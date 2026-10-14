"""Opt-in, content-addressed boot profile policy for complete watch stores.

This composes boot policy only. It never creates feeds, downloads images, edits
partitions, removes baseline files, or treats a source fixture as an admission.
"""
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

REQUEST = {'capability': 'platform.provision-request', 'api': 1}
PRODUCTS = {'wave': 'waveshare-s3-touch-amoled-206', 'twatch': 'twatch-s3'}
MAX_FILES = 160
MAX_MIRRORS = 64
MAX_IMAGE_BYTES = 2 * 1024 * 1024
REPLACED = {'boot.json', 'cohort.json', 'default.json', 'default.elf',
            'springboard.json', 'springboard.elf'}


def read_json(path):
    return json.loads(Path(path).read_text())


def inventory(root):
    root = Path(root)
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Store symlinks are not supported: ' + str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def relative_file(root, relative):
    path = PurePosixPath(relative)
    if not relative or path.is_absolute() or '..' in path.parts or str(path) != relative:
        raise ValueError('Unsafe store path: ' + repr(relative))
    result = Path(root) / path
    if not result.is_file() or result.is_symlink():
        raise ValueError('Missing internal fallback file: ' + relative)
    return result


def image_file(root, entry, preserve_external_only=False):
    manifest_path = relative_file(root, entry['manifest'])
    manifest = read_json(manifest_path)
    name = manifest['file_name']
    if PurePosixPath(name).name != name or not name.endswith('.elf'):
        raise ValueError('Invalid manifest ELF filename: ' + repr(name))
    relative = str(PurePosixPath(entry['manifest']).parent / name)
    source = entry.get('image_source', {})
    if (preserve_external_only and not (Path(root) / relative).exists()
            and source.get('volume_instance') == 12 and source.get('path')
            and not source.get('internal_fallback')):
        # Preserve pre-existing optional SD-only features without inventing a
        # fallback or admitting their remote contents into the core profile.
        return manifest, None
    return manifest, relative_file(root, relative)


def validate_inputs(catalog, product, native_provider_manifests):
    if native_provider_manifests is None:
        raise ValueError('--boot-profiles requires --native-provider-manifests (JSON list, [] if none)')
    selected = read_json(native_provider_manifests)
    if (not isinstance(selected, list) or any(not isinstance(x, str) for x in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError('Native provider manifests must be a unique JSON string list')
    manifest = read_json(Path(catalog) / 'manifest.json')
    receipt = read_json(Path(catalog) / 'build.json')
    if (manifest.get('id') != 'installed-apps' or
            {'capability': 'platform.package-volume', 'api': 1} not in manifest.get('requires', [])):
        raise ValueError('Catalog must retain its installed-apps identity and native package-volume declaration')
    if REQUEST not in manifest.get('requires', []):
        raise ValueError('Catalog must be built with --boot-profiles')
    if not all(receipt.get(flag) is True for flag in ['boot_profiles', 'native_feed', 'internal_packages']):
        raise ValueError('Catalog requires --boot-profiles --native-feed --internal-packages')
    if receipt.get('feed_product') != PRODUCTS[product]:
        raise ValueError('Catalog feed product does not match product composition')
    if not isinstance(receipt.get('feed_url'), str) or not receipt['feed_url'].startswith('https://'):
        raise ValueError('Catalog requires an explicit product-owned HTTPS feed URL')
    if receipt.get('elf_sha256') != hashlib.sha256((Path(catalog) / 'driver.elf').read_bytes()).hexdigest():
        raise ValueError('Catalog ELF does not match its build receipt')
    return selected


def verify_runtime_version(version, firmware):
    """Match canonical native version to the actual firmware payload marker."""
    if (not isinstance(version, str) or len(version) >= 32 or
            not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version) or
            any(int(part) > 0xffffffff for part in version.split('.'))):
        raise ValueError('--runtime-version must be a canonical bounded three-part native version')
    marker = b'RISC_RUNTIME_VERSION:'
    matches = re.findall(rb'RISC_RUNTIME_VERSION:([^\x00]*)\x00', firmware)
    # NativeBankStore also embeds the empty parser-prefix string. It carries no
    # version identity; all nonempty markers must still match the requested one.
    versions = {match for match in matches if match}
    if firmware.count(marker) != len(matches) or versions != {version.encode('ascii')}:
        raise ValueError('--runtime-version does not match the exact firmware native version marker')
    return version


def dependencies(boot, manifests):
    """Conservative software graph; retain every matching unbound provider."""
    drivers = boot['drivers']
    edges = [set() for _ in drivers]
    for index, (entry, manifest) in enumerate(zip(drivers, manifests)):
        for requirement in manifest.get('requires', []) + manifest.get('optional', []):
            bindings = [b for b in entry.get('bindings', [])
                        if b['capability'] == requirement['capability'] and b['api'] == requirement['api']]
            if len(bindings) > 1:
                raise ValueError('Ambiguous provider binding: ' + entry['manifest'])
            for target, (provider, exported) in enumerate(zip(drivers, manifests)):
                if bindings and provider.get('instance_id', 0) != bindings[0]['instance_id']:
                    continue
                if any(p['capability'] == requirement['capability'] and p['api'] == requirement['api']
                       for p in exported.get('provides', [])):
                    edges[index].add(target)
    return edges


def assert_acyclic(edges):
    active, complete = set(), set()
    def visit(index):
        if index in active:
            raise ValueError('Provider dependency/image-source cycle')
        if index in complete:
            return
        active.add(index)
        for target in edges[index]:
            visit(target)
        active.remove(index)
        complete.add(index)
    for index in range(len(edges)):
        visit(index)


def compose(boot, store, product, native_provider_manifests):
    """Mutate only image_source policy; every fallback is an existing exact ELF."""
    drivers = boot['drivers']
    driver_images = [image_file(store, entry) for entry in drivers]
    app_images = [image_file(store, entry, preserve_external_only=product == 'wave')
                  for entry in boot['app_capabilities']]
    manifests = [manifest for manifest, _ in driver_images]
    native_names = set(native_provider_manifests)
    unknown = native_names - {entry['manifest'] for entry in drivers}
    if unknown:
        raise ValueError('Native-selected provider absent from boot: ' + repr(sorted(unknown)))
    edges = dependencies(boot, manifests)
    assert_acyclic(edges)
    storage = {i for i, manifest in enumerate(manifests)
               if any(p['capability'] == 'storage.volume' for p in manifest.get('provides', []))}
    protected = storage | {i for i, entry in enumerate(drivers) if entry['manifest'] in native_names}
    pending = list(protected)
    while pending:
        index = pending.pop()
        for dependency in edges[index] - protected:
            protected.add(dependency)
            pending.append(dependency)
    mirrors = {}
    external_only = []
    if product == 'twatch':
        if any(d.get('image_source') for d in drivers + boot['app_capabilities']):
            raise ValueError('T-Watch internal-only profile cannot retain an external image_source')
        if boot['installation'].get('volume_instance') != 0 or boot['installation'].get('internal_volume_instance') != 0:
            raise ValueError('T-Watch package volumes must remain internal')
        if any(drivers[i].get('instance_id', 0) != 0 for i in storage):
            raise ValueError('T-Watch profile cannot add a removable storage provider')
    elif product == 'wave':
        sd = [i for i in storage if drivers[i].get('instance_id') == 12 and
              {'capability': 'storage.volume', 'api': 1} in manifests[i].get('provides', [])]
        if len(sd) != 1:
            raise ValueError('Waveshare requires exactly one boot-owned SD volume12')
        def mirror(entry, manifest, image, prefix):
            identifier = manifest['id']
            if not re.fullmatch(r'[a-z0-9_-]+', identifier):
                raise ValueError('Core mirror ID is not supported: ' + identifier)
            content = image.read_bytes()
            if not content or len(content) > MAX_IMAGE_BYTES:
                raise ValueError('Core mirror ELF size is outside the consumer bound: ' + str(image))
            digest = hashlib.sha256(content).hexdigest()
            path = prefix + '/' + identifier + '/image-' + digest + '.elf'
            entry['image_source'] = {'volume_instance': 12, 'path': path, 'internal_fallback': True}
            mirrors[path] = {'manifest': entry['manifest'], 'sha256': digest, 'bytes': len(content)}
        for index, (entry, (manifest, image)) in enumerate(zip(drivers, driver_images)):
            if index in protected:
                if 'image_source' in entry:
                    raise ValueError('Native/storage bootstrap dependency must already be internal: ' + entry['manifest'])
            else:
                mirror(entry, manifest, image, 'Drivers')
                edges[index].add(sd[0])
        for entry, (manifest, image) in zip(boot['app_capabilities'], app_images):
            if image is None:
                external_only.append(entry['manifest'])
                continue
            if entry.get('catalog_authority'):
                raise ValueError('Core composition requires boot-owned apps, not catalog reservations')
            mirror(entry, manifest, image, 'Apps')
        if len(mirrors) > MAX_MIRRORS:
            raise ValueError('Core mirror count exceeds service maximum 64')
        assert_acyclic(edges)
    else:
        raise ValueError('Unknown product: ' + product)
    return {'product': PRODUCTS[product], 'native_provider_manifests': sorted(native_names),
            'internal_provider_closure': sorted(drivers[i]['manifest'] for i in protected),
            'external_only_apps_preserved': external_only,
            'mirror_count': len(mirrors), 'mirrors': mirrors}


def verify_preservation(baseline, output):
    before, after = inventory(baseline), inventory(output)
    missing = before.keys() - after.keys()
    if missing:
        raise ValueError('Baseline files were removed: ' + repr(sorted(missing)))
    changed = {name for name in before if before[name] != after[name]}
    if changed - REPLACED:
        raise ValueError('Unapproved baseline file replacements: ' + repr(sorted(changed - REPLACED)))
    for name in ['default.json', 'springboard.json']:
        original, replacement = read_json(Path(baseline) / name), read_json(Path(output) / name)
        if any(original.get(key) != replacement.get(key) for key in ['id', 'file_name', 'type']):
            raise ValueError('Replacement changed an existing app identity: ' + name)
    if len(after) > MAX_FILES:
        raise ValueError('Complete store exceeds native provisioning maximum 160 files')
    return {'baseline_file_count': len(before), 'output_file_count': len(after),
            'replaced_files': sorted(changed), 'added_files': sorted(after.keys() - before.keys()),
            'files': after}
