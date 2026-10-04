#!/usr/bin/env python3
"""Publish the accepted Watch baseline unchanged; never access a physical device.

Products use Reader's immutable release/index protocol. Components retain their
own versions. Accepted Watch ELFs, not generic shared-app builds, are published.
"""
import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import zipfile
from watch_release_index import EMPTY_INDEX, REPOSITORY, require, serialize_index, update_index

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'release/product.json'


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def command(*args, cwd=ROOT):
    return subprocess.check_output(list(map(str, args)), cwd=cwd)


def gh(*args):
    return command('gh', *args)


def api(endpoint):
    return json.loads(gh('api', endpoint))


def read_config():
    p = json.loads(CONFIG.read_text())
    require(p['schema'] == 1 and p['repository'] == REPOSITORY, 'Product identity mismatch')
    require(p['tag'] == 'firmware-v' + p['version'], 'Product tag/version mismatch')
    require(p['component_versions']['default'] == p['accepted_build'], 'Accepted component mismatch')
    return p


def checked_zip(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    require(len(names) <= 1000 and len(names) == len(set(names)), 'ZIP inventory invalid')
    require(sum(x.file_size for x in z.infolist()) <= 160 * 1024 * 1024, 'ZIP too large')
    require(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in names), 'Unsafe ZIP path')
    require(z.testzip() is None, 'ZIP CRC failure')
    return z


def archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            z.writestr(entry, data)
    return output.getvalue()


def artifact_inputs(directory, download=False):
    p = read_config()
    directory.mkdir(parents=True, exist_ok=True)
    for name, item in p['artifacts'].items():
        path = directory / (name + '.zip')
        if download:
            metadata = api(f'repos/{item["repository"]}/actions/artifacts/{item["artifact_id"]}')
            require(not metadata['expired'] and metadata['workflow_run']['id'] == item['run_id'], 'Wrong or expired artifact')
            data = gh('api', f'repos/{item["repository"]}/actions/artifacts/{item["artifact_id"]}/zip')
            require(sha(data) == item['sha256'], 'Downloaded artifact hash mismatch')
            path.write_bytes(data)
        require(path.is_file() and not path.is_symlink() and sha(path.read_bytes()) == item['sha256'], 'Accepted input hash mismatch: ' + name)
        checked_zip(path.read_bytes()).close()
    return p


def record(kind, identity, version, asset, data, **extra):
    tag = f'{kind}-' + (identity + '-' if identity else '') + 'v' + version
    return {'kind': kind, **({'id': identity} if identity else {}), 'version': version,
            'tag': tag, 'asset': asset,
            'url': f'https://github.com/{REPOSITORY}/releases/download/{tag}/{asset}',
            'size': len(data), 'sha256': sha(data), **extra}


def flashing_document(p):
    name = f'twatch-s3-launcher-{p["version"]}.bin'
    return f'''# Watch {p['version']}\n\nOriginal/non-Plus LILYGO T-Watch-S3, 16 MiB flash / 8 MiB OPI PSRAM.\n\nFlashable merged image: {name}, offset 0x0, exactly 8 MiB.\nSHA256: {p['accepted_bin_sha256']}\n\nThis is byte-for-byte the owner-accepted 0.5.2 integrated build, promoted to\nproduct 1.0.0. Clock remains 0.5.2 and Runtime remains 0.1.6. No firmware,\napplication, driver, board, grant, or persistent-store byte was changed.\n\nWARNING: flashing replaces the lower 8 MiB, including NVS/settings and saved\nStopwatch state. Upper 8 MiB is untouched. Back up first. No device was flashed\nby the release process. This is not an OTA update or a settings-preserving update.\n\nAfter your own backup and device selection:\npython -m esptool --chip esp32s3 --port PORT --baud 460800 write_flash 0x0 {name}\n\nThe original 0.5.2 custody ZIP is preserved unchanged; its historical pending\nhardware wording records the pre-delivery build state. Product provenance records\nthe subsequent owner acceptance, which does not qualify every optional peripheral.\n\nIndependent app ELFs/manifests use this Watch configuration. Drivers retain their\nexisting package ABI and versions. Merely downloading an ELF does not install it;\nuse the exact manifests, board mapping and grants in the custody bundle.\n'''.encode()

def stage(inputs, accepted_watch, runtime_source, output):
    p = artifact_inputs(inputs)
    for path, key in ((accepted_watch, 'watch'), (runtime_source, 'runtime')):
        require(command('git', 'rev-parse', 'HEAD', cwd=path).decode().strip() == p['sources'][key]['accepted_sha'], 'Source checkout mismatch')
        require(not command('git', 'status', '--porcelain', '--untracked-files=no', cwd=path).strip(), 'Source checkout dirty')
    output.mkdir(parents=True, exist_ok=True)
    source = command('git', 'rev-parse', 'HEAD').decode().strip()
    with tempfile.TemporaryDirectory() as tmp:
        built = Path(tmp) / 'accepted'
        subprocess.run(['python', str(accepted_watch / 'scripts/build_launcher_flash_bundle.py'),
                        '--runtime', str(inputs / 'runtime.zip'), '--artifact', str(inputs / 'launcher.zip'),
                        '--pr-head', p['sources']['watch']['accepted_sha'], '--runtime-source', str(runtime_source),
                        '--output', str(built)], check=True)
        accepted_bin = (built / f'twatch-s3-launcher-{p["accepted_build"]}.bin').read_bytes()
        accepted_bundle = (built / f'twatch-s3-launcher-{p["accepted_build"]}-flashing.zip').read_bytes()
    require(len(accepted_bin) == p['bin_size'] and sha(accepted_bin) == p['accepted_bin_sha256'], 'Hardware-accepted BIN differs')
    require(sha(accepted_bundle) == p['accepted_bundle_sha256'], 'Original custody ZIP differs')
    with checked_zip(accepted_bundle) as z:
        files = {n: z.read(n) for n in z.namelist()}
    accepted_manifest = json.loads(files['manifest.json'])
    for item in accepted_manifest['store']:
        data = files['store/' + item['path']]
        require(len(data) == item['size_bytes'] and sha(data) == item['sha256'], 'Store custody mismatch')
    licenses = archive({n: b for n, b in files.items() if n.startswith(('licenses/', 'shared/')) or n == 'reproduce/RUNTIME-LICENSE'})
    provenance = {**p, 'release_source_sha': source, 'binary_rebuilt': False,
                  'version_scope': 'Product release only; every embedded component version and byte is unchanged.',
                  'hardware_acceptance_scope': 'Owner accepted this exact integrated Watch BIN. No additional physical testing or peripheral qualification is claimed.',
                  'accepted_manifest': accepted_manifest}
    release_list = []
    app_records = []
    for name in ('default', 'clock', 'springboard', 'settings', 'battery', 'calculator', 'stopwatch'):
        manifest_data = files['store/' + name + '.json']
        manifest = json.loads(manifest_data)
        data = files['store/' + name + '.elf']
        require(manifest['version'] == p['component_versions'][name], 'Component version changed')
        require(data[:7] == b'\x7fELF\x01\x01\x01' and data[16:20] == b'\x03\x00\x5e\x00', 'Invalid Xtensa application')
        r = record('app', name, manifest['version'], name + '.elf', data, manifest=manifest,
                   source_repo=REPOSITORY, source_sha=p['sources']['watch']['accepted_sha'],
                   build_sources=p['sources'], configuration='accepted-watch-0.5.2')
        app_records.append(r)
        payloads = {name + '.elf': data, name + '.json': manifest_data, 'LICENSES.zip': licenses,
                    'release-record.json': encoded(r)}
        release_list.append(write_release(output, r, payloads, p['sources']['watch']['accepted_sha'], False))
    (output / 'accepted-driver-artifact.zip').write_bytes((inputs / 'drivers.zip').read_bytes())
    driver_records = []
    with checked_zip((inputs / 'drivers.zip').read_bytes()) as z:
        catalog = json.loads(z.read('catalog.json'))
        require(len(catalog['packages']) == 17, 'Expected complete driver catalog')
        for entry in catalog['packages']:
            data = z.read(entry['archive'])
            require(len(data) == entry['size_bytes'] and sha(data) == entry['sha256'], 'Driver archive custody mismatch')
            with checked_zip(data) as package:
                manifest = json.loads(package.read('.package.json'))
                require(manifest['id'] == entry['id'] and manifest['version'] == entry['version'], 'Driver identity mismatch')
                require(set(package.namelist()) == {x['name'] for x in manifest['entries']} | {'.package.json'}, 'Driver member mismatch')
                for item in manifest['entries']:
                    payload = package.read(item['name'])
                    require(len(payload) == item['size_bytes'] and sha(payload) == item['sha256'], 'Driver payload mismatch')
                short = entry['id'].removeprefix('twatch-')
                deployed = 'store/' + short + '/driver.elf'
                if deployed in files:
                    require(package.read('driver.elf') == files[deployed], 'Independent driver differs from accepted BIN')
                    require(json.loads(package.read('source-manifest.json')) == json.loads(files['store/' + short + '/manifest.json']), 'Driver manifest differs from accepted BIN')
            r = record('driver', entry['id'], entry['version'], entry['archive'], data,
                       format='rte.zip', architecture='xtensa-esp32s3', manifest=manifest,
                       source_repo=REPOSITORY, included_in_accepted_bin=deployed in files)
            driver_records.append(r)
            destination = output / 'driver-assets' / entry['archive']
            destination.parent.mkdir(exist_ok=True)
            destination.write_bytes(data)
    name = f'twatch-s3-launcher-{p["version"]}.bin'
    firmware = record('firmware', '', p['version'], name, accepted_bin, source_sha=source,
                      accepted_source_sha=p['sources']['watch']['accepted_sha'], component_versions=p['component_versions'])
    index = copy.deepcopy(EMPTY_INDEX)
    index = update_index(index, 'firmware', firmware)
    for r in app_records:
        index = update_index(index, 'apps', r)
    for r in driver_records:
        index = update_index(index, 'drivers', r)
    flashing = flashing_document(p)
    payloads = {name: accepted_bin, f'twatch-s3-launcher-{p["accepted_build"]}-flashing.zip': accepted_bundle,
                'release-record.json': encoded(firmware), 'product-provenance.json': encoded(provenance),
                'release-index.json': serialize_index(index).encode(), 'FLASHING.md': flashing}
    release_list.append(write_release(output, firmware, payloads, source, True))
    plan = {'schema': 1, 'repository': REPOSITORY, 'source_sha': source, 'product': p,
            'releases': release_list, 'driver_records': driver_records, 'index': index}
    (output / 'publication-plan.json').write_bytes(encoded(plan))
    verify_stage(output)
    print(f'Staged Watch {p["version"]}: exact accepted BIN, seven apps, seventeen driver references')


def write_release(output, record, files, source, latest):
    sums = ''.join(f'{sha(data)}  {name}\n' for name, data in sorted(files.items()))
    files['SHA256SUMS'] = sums.encode()
    directory = output / record['tag']
    directory.mkdir(exist_ok=True)
    for name, data in files.items():
        require(PurePosixPath(name).name == name, 'Release asset must be a basename')
        (directory / name).write_bytes(data)
    return {'tag': record['tag'], 'source_sha': source, 'latest': latest,
            'assets': {name: {'size': len(data), 'sha256': sha(data)} for name, data in sorted(files.items())}}


def verify_stage(output):
    plan = json.loads((output / 'publication-plan.json').read_text())
    p = read_config()
    source = command('git', 'rev-parse', 'HEAD').decode().strip()
    require(plan['schema'] == 1 and plan['repository'] == REPOSITORY and plan['product'] == p, 'Staged product mismatch')
    require(plan['source_sha'] == source, 'Stage belongs to another release commit')
    firmware_dir = output / p['tag']
    bundle_name = f'twatch-s3-launcher-{p["accepted_build"]}-flashing.zip'
    bundle = (firmware_dir / bundle_name).read_bytes()
    require(sha(bundle) == p['accepted_bundle_sha256'], 'Original accepted custody ZIP changed')
    with checked_zip(bundle) as z:
        frozen = {n: z.read(n) for n in z.namelist()}
    original_bin = frozen[f'twatch-s3-launcher-{p["accepted_build"]}.bin']
    require(len(original_bin) == p['bin_size'] and sha(original_bin) == p['accepted_bin_sha256'], 'Accepted ZIP/BIN mismatch')
    licenses = archive({n: b for n, b in frozen.items() if n.startswith(('licenses/', 'shared/')) or n == 'reproduce/RUNTIME-LICENSE'})
    expected = {}
    index = copy.deepcopy(EMPTY_INDEX)
    for name in ('default', 'clock', 'springboard', 'settings', 'battery', 'calculator', 'stopwatch'):
        manifest_data, data = frozen['store/' + name + '.json'], frozen['store/' + name + '.elf']
        manifest = json.loads(manifest_data)
        require(manifest['version'] == p['component_versions'][name], 'Accepted app version mismatch')
        r = record('app', name, manifest['version'], name + '.elf', data, manifest=manifest,
                   source_repo=REPOSITORY, source_sha=p['sources']['watch']['accepted_sha'],
                   build_sources=p['sources'], configuration='accepted-watch-0.5.2')
        index = update_index(index, 'apps', r)
        payloads = {name + '.elf': data, name + '.json': manifest_data, 'LICENSES.zip': licenses,
                    'release-record.json': encoded(r)}
        expected[r['tag']] = (payloads, p['sources']['watch']['accepted_sha'], False)
    artifact = (output / 'accepted-driver-artifact.zip').read_bytes()
    require(sha(artifact) == p['artifacts']['drivers']['sha256'], 'Accepted driver artifact changed')
    driver_records = []
    with checked_zip(artifact) as z:
        catalog = json.loads(z.read('catalog.json'))
        require(len(catalog['packages']) == 17, 'Incomplete accepted driver catalog')
        for item in catalog['packages']:
            data = z.read(item['archive'])
            require(len(data) == item['size_bytes'] and sha(data) == item['sha256'], 'Accepted driver catalog mismatch')
            with checked_zip(data) as package:
                manifest = json.loads(package.read('.package.json'))
            deployed = 'store/' + item['id'].removeprefix('twatch-') + '/driver.elf'
            r = record('driver', item['id'], item['version'], item['archive'], data,
                       format='rte.zip', architecture='xtensa-esp32s3', manifest=manifest,
                       source_repo=REPOSITORY, included_in_accepted_bin=deployed in frozen)
            driver_records.append(r)
            path = output / 'driver-assets' / r['asset']
            require(path.is_file() and not path.is_symlink() and path.read_bytes() == data, 'Staged driver changed')
            index = update_index(index, 'drivers', r)
    name = f'twatch-s3-launcher-{p["version"]}.bin'
    firmware = record('firmware', '', p['version'], name, original_bin, source_sha=source,
                      accepted_source_sha=p['sources']['watch']['accepted_sha'], component_versions=p['component_versions'])
    index = update_index(index, 'firmware', firmware)
    require(plan['index'] == index and plan['driver_records'] == driver_records, 'Publication/index records differ from accepted components')
    provenance = {**p, 'release_source_sha': source, 'binary_rebuilt': False,
                  'version_scope': 'Product release only; every embedded component version and byte is unchanged.',
                  'hardware_acceptance_scope': 'Owner accepted this exact integrated Watch BIN. No additional physical testing or peripheral qualification is claimed.',
                  'accepted_manifest': json.loads(frozen['manifest.json'])}
    flashing = flashing_document(p)
    payloads = {name: original_bin, bundle_name: bundle, 'release-record.json': encoded(firmware),
                'product-provenance.json': encoded(provenance), 'release-index.json': serialize_index(index).encode(),
                'FLASHING.md': flashing}
    expected[p['tag']] = (payloads, source, True)
    require(len(plan['releases']) == len(expected) and {r['tag'] for r in plan['releases']} == set(expected), 'Wrong release inventory')
    for release in plan['releases']:
        payloads, target, latest = expected[release['tag']]
        payloads['SHA256SUMS'] = ''.join(f'{sha(data)}  {name}\n' for name, data in sorted(payloads.items())).encode()
        require(release['source_sha'] == target and release['latest'] is latest, 'Wrong release source or latest flag')
        exact_assets = {name: {'size': len(data), 'sha256': sha(data)} for name, data in sorted(payloads.items())}
        require(release['assets'] == exact_assets, 'Asset record differs from accepted payloads')
        directory = output / release['tag']
        require({x.name for x in directory.iterdir()} == set(payloads), 'Unexpected staged assets')
        for name, data in payloads.items():
            path = directory / name
            require(path.is_file() and not path.is_symlink() and path.read_bytes() == data, 'Staged asset differs from accepted bytes')
    return plan


def release_by_tag(tag):
    # Tag-specific REST lookup omits drafts. Listing includes owned drafts;
    # use the stable creation ID below when verifying a newly created draft.
    pages = json.loads(gh('api', f'repos/{REPOSITORY}/releases?per_page=100', '--paginate', '--slurp'))
    matches = [r for page in pages for r in page if r['tag_name'] == tag]
    require(len(matches) <= 1, 'Duplicate release tag')
    return matches[0] if matches else None


def verify_downloads(release, expected, destination):
    names = [a['name'] for a in release['assets']]
    require(len(names) == len(set(names)) and set(names) == set(expected), 'Release inventory mismatch')
    destination.mkdir()
    for asset in release['assets']:
        data = gh('api', f'repos/{REPOSITORY}/releases/assets/{asset["id"]}', '-H', 'Accept: application/octet-stream')
        (destination / asset['name']).write_bytes(data)
    require({p.name for p in destination.iterdir()} == set(expected), 'Downloaded inventory mismatch')
    for name, meta in expected.items():
        data = (destination / name).read_bytes()
        require(len(data) == meta['size'] and sha(data) == meta['sha256'], 'Downloaded release bytes differ')


def publish_one(release, output):
    tag = release['tag']
    target = release['source_sha']
    existing = release_by_tag(tag)
    tag_lookup = subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/git/ref/tags/{tag}'], cwd=ROOT, capture_output=True)
    if tag_lookup.returncode == 0:
        require(api(f'repos/{REPOSITORY}/commits/{tag}')['sha'] == target, 'Existing tag source collision')
    else:
        require(b'HTTP 404' in tag_lookup.stderr, 'Tag lookup failed')
    if existing is None:
        notes = ('Watch 1.0.0 stable baseline. Exact owner-accepted 0.5.2 bytes; component versions retained. '
                 'Flash offset 0x0 replaces lower 8 MiB including settings. See FLASHING.md and product-provenance.json.'
                 if release['latest'] else 'Independent accepted Watch-configured application. '
                 'ELF and manifest are byte-identical to the accepted Watch 0.5.2 deployment. '
                 'Component version is unchanged. See release-record.json and LICENSES.zip; no device installation performed.')
        existing = json.loads(gh('api', f'repos/{REPOSITORY}/releases', '--method', 'POST',
                                 '-f', 'tag_name=' + tag, '-f', 'target_commitish=' + target,
                                 '-f', 'name=' + ('Watch 1.0.0' if release['latest'] else tag),
                                 '-f', 'body=' + notes, '-F', 'draft=true'))
    require(existing['target_commitish'] == target, 'Existing release source collision')
    require(not existing.get('prerelease', False), 'Stable release cannot resume a prerelease')
    names = [a['name'] for a in existing['assets']]
    require(len(names) == len(set(names)) and set(names) <= set(release['assets']), 'Unexpected existing assets')
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name in names:
            destination = tmp / name
            asset = next(a for a in existing['assets'] if a['name'] == name)
            destination.write_bytes(gh('api', f'repos/{REPOSITORY}/releases/assets/{asset["id"]}', '-H', 'Accept: application/octet-stream'))
            require(destination.read_bytes() == (output / tag / name).read_bytes(), 'Immutable uploaded asset collision')
        for name in sorted(set(release['assets']) - set(names)):
            require(existing['draft'], 'Published release has missing assets')
            gh('api', f'https://uploads.github.com/repos/{REPOSITORY}/releases/{existing["id"]}/assets?name={name}', '--method', 'POST', '--input', output / tag / name, '-H', 'Content-Type: application/octet-stream')
        uploaded = api(f'repos/{REPOSITORY}/releases/{existing["id"]}')
        require(uploaded is not None, 'Cannot verify uploaded draft')
        verify_downloads(uploaded, release['assets'], tmp / 'verify')
    if existing['draft']:
        gh('api', f'repos/{REPOSITORY}/releases/{existing["id"]}', '--method', 'PATCH', '-F', 'draft=false', '-f', 'make_latest=' + str(release['latest']).lower())
    published = api(f'repos/{REPOSITORY}/releases/{existing["id"]}')
    require(published is not None and not published['draft'], 'Publication not confirmed')
    require(api(f'repos/{REPOSITORY}/commits/{tag}')['sha'] == target, 'Published tag source mismatch')
    print('Verified release:', published['html_url'])


def verify_driver_releases(plan, output):
    # Driver automation retains its original immutable catalog/release records.
    # Download the live asset and compare it with accepted CI, not a fresh build.
    for r in plan['driver_records']:
        release = release_by_tag(r['tag'])
        require(release is not None and not release['draft'], 'Driver publication still pending: ' + r['tag'])
        require({a['name'] for a in release['assets']} == {r['asset'], 'release-record.json'}, 'Driver release inventory differs')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            for asset in release['assets']:
                (path / asset['name']).write_bytes(gh('api', f'repos/{REPOSITORY}/releases/assets/{asset["id"]}', '-H', 'Accept: application/octet-stream'))
            require((path / r['asset']).read_bytes() == (output / 'driver-assets' / r['asset']).read_bytes(), 'Published driver differs from accepted source')
            record = json.loads((path / 'release-record.json').read_text())
        require(record['id'] == r['id'] and record['version'] == r['version'] and record['sha256'] == r['sha256'] and record['size_bytes'] == r['size'], 'Driver release record mismatch')
        require(api(f'repos/{REPOSITORY}/commits/{r["tag"]}')['sha'] == record['source_sha'], 'Driver tag source mismatch')


def publish_index(index):
    # Same branch-only, monotonic, non-force protocol as Reader. Plumbing avoids
    # copying main's source files into the dedicated index branch.
    old = command('git', 'ls-remote', 'origin', 'refs/heads/release-index').decode().strip()
    parent = old.split()[0] if old else None
    current = copy.deepcopy(EMPTY_INDEX)
    if parent:
        command('git', 'fetch', 'origin', 'refs/heads/release-index')
        require(command('git', 'rev-parse', 'FETCH_HEAD').decode().strip() == parent, 'Index changed while fetching')
        current = json.loads(command('git', 'show', parent + ':release-index.json'))
    result = update_index(current, 'firmware', index['firmware'])
    for product in ('apps', 'drivers'):
        for r in index[product]:
            result = update_index(result, product, r)
    if current == result:
        print('Release index already verified unchanged')
        return
    data = serialize_index(result).encode()
    blob = subprocess.check_output(['git', 'hash-object', '-w', '--stdin'], input=data, cwd=ROOT).decode().strip()
    tree = subprocess.check_output(['git', 'mktree'], input=f'100644 blob {blob}\trelease-index.json\n'.encode(), cwd=ROOT).decode().strip()
    args = ['git', '-c', 'user.name=github-actions[bot]', '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com', 'commit-tree', tree]
    if parent:
        args += ['-p', parent]
    commit = subprocess.check_output(args + ['-m', 'Index verified Watch 1.0.0 baseline and independent components'], cwd=ROOT).decode().strip()
    command('git', 'push', 'origin', commit + ':refs/heads/release-index')
    require(command('git', 'ls-remote', 'origin', 'refs/heads/release-index').decode().split()[0] == commit, 'Index publication not confirmed')
    print('Verified release index:', f'https://github.com/{REPOSITORY}/blob/release-index/release-index.json')


def publish(output):
    plan = verify_stage(output)
    repository = api('repos/' + REPOSITORY)
    require(os.environ.get('GITHUB_REPOSITORY') == REPOSITORY, 'Wrong publishing repository')
    require(os.environ.get('GITHUB_REF') == 'refs/heads/' + repository['default_branch'], 'Publication requires current default branch')
    require(os.environ.get('GITHUB_EVENT_NAME') in ('push', 'workflow_dispatch', 'workflow_run'), 'Publication requires default-branch release workflow or explicit dispatch')
    require(api(f'repos/{REPOSITORY}/commits/{repository["default_branch"]}')['sha'] == plan['source_sha'], 'Default branch advanced; review current release source')
    verify_driver_releases(plan, output)
    for r in plan['releases']:
        publish_one(r, output)
    publish_index(plan['index'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['download', 'stage', 'verify', 'publish'])
    parser.add_argument('--inputs', type=Path, default=ROOT / 'dist/product-inputs')
    parser.add_argument('--accepted-watch', type=Path)
    parser.add_argument('--runtime-source', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/watch-product')
    a = parser.parse_args()
    if a.action == 'download':
        artifact_inputs(a.inputs.resolve(), download=True)
    elif a.action == 'stage':
        require(a.accepted_watch and a.runtime_source, 'Exact accepted source checkouts required')
        stage(a.inputs.resolve(), a.accepted_watch.resolve(), a.runtime_source.resolve(), a.output.resolve())
    elif a.action == 'verify':
        verify_stage(a.output.resolve())
    else:
        publish(a.output.resolve())
