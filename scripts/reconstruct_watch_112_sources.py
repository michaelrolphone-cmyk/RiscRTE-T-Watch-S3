#!/usr/bin/env python3
"""Restore original Watch 1.0.12 source identities from public Git plus bundles.

Run hydrate before build. Compilation creates fresh evidence and never changes,
relabels, uploads or replaces the accepted release. Uses only Python stdlib.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

CUSTODY_SHA = '73f36c7057dbe71525518fe5e80aa018a4ee03621f618fcf9c38aaef50c441d8'
BUILD_INPUTS_SHA = 'a65b56c15461807c197c7dbbc8b0eb585a9d1a242f5063f96f011c6829670be3'
BUILD_INPUTS_SIZE = 13171498
BUILD_INPUTS_GZIP_SHA = '1ec9d40a70552217b11ca9be16f571a022259f9b9a028cd10f28fc56f60367fd'
BUILD_INPUTS_GZIP_SIZE = 12992847
BUILD_INPUT_PART_NAMES = ('reconstruction-inputs.zip.gz.part1', 'reconstruction-inputs.zip.gz.part2')
IMAGE_SHA = 'af958e480a3183bde3f448e97930d56b9aeea567a664428892b917a878d014ff'
DRIVERS_SHA = '4088b6892c2e2654b0342f04a7d191068e4a8e2e'
# Six Arduino assertion/log strings retain this original package prefix.
# This is a compiler string mapping, not a required filesystem location.
ACCEPTED_PACKAGE_PREFIX = '/workspace/scratch/c744abbbbd60/watch-build-tools/platformio-core/packages'
REPOSITORIES = {'RiscRTE-T-Watch-S3', 'RiscRTE', 'RiscRTE-System-Apps', 'RiscRTE-Utilities', 'RiscRTE-Productivity'}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def run(*args, cwd=None, env=None):
    subprocess.run(list(map(str, args)), cwd=cwd, env=env, check=True)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def bounded_read(path, limit):
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'Reconstruction input exceeds size limit: ' + str(path))
    return raw


def build_inputs_bytes(paths):
    """Accept the published ZIP or its two pinned Git transport parts."""
    if isinstance(paths, Path):
        raw = bounded_read(paths, BUILD_INPUTS_SIZE)
    else:
        require(len(paths) == 2, 'Exactly two compressed reconstruction parts required')
        raw = b''.join(bounded_read(path, BUILD_INPUTS_GZIP_SIZE // 2 + 1) for path in paths)
        require(len(raw) == BUILD_INPUTS_GZIP_SIZE and sha(raw) == BUILD_INPUTS_GZIP_SHA,
                'Compressed reconstruction input custody differs')
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            raw = stream.read(BUILD_INPUTS_SIZE + 1)
    require(len(raw) == BUILD_INPUTS_SIZE, 'Expanded reconstruction input size differs')
    require(sha(raw) == BUILD_INPUTS_SHA, 'Archive custody differs: reconstruction inputs')
    return raw


def archive_members(raw, expected, label='archive'):
    require(sha(raw) == expected, 'Archive custody differs: ' + str(label))
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) <= 1000 and sum(v.file_size for v in archive.infolist()) <= 160 * 1024 * 1024,
                'Unbounded or duplicate archive inventory')
        for entry in archive.infolist():
            p = PurePosixPath(entry.filename)
            require(not entry.is_dir() and not p.is_absolute() and '..' not in p.parts and
                    '\\' not in entry.filename and str(p) == entry.filename and
                    (entry.external_attr >> 16) & 0o170000 != 0o120000, 'Unsafe archive member')
        return {name: archive.read(name) for name in names}


def members(path, expected):
    return archive_members(path.read_bytes(), expected, path)


def extract(files, root):
    require(not root.exists(), 'Refusing to replace output: ' + str(root))
    root.mkdir(parents=True)
    for name, raw in files.items():
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)


def fetch(root, repository, commit):
    require(re.fullmatch('[0-9a-f]{40}', commit), 'Exact public commit required')
    require(not root.exists(), 'Refusing to replace source checkout: ' + str(root))
    root.mkdir(parents=True)
    run('git', 'init', root)
    run('git', '-C', root, 'remote', 'add', 'origin', 'https://github.com/' + repository + '.git')
    # Full commit ancestry is needed by the incremental bundle verification.
    run('git', '-C', root, 'fetch', '--filter=blob:none', 'origin', commit)


def validate_mapping(custody):
    mapping = json.loads(custody['source-equivalence.json'])
    require(mapping['full_image_sha256'] == IMAGE_SHA and len(mapping['sources']) == 5, 'Wrong accepted source mapping')
    require({v['repository'] for v in mapping['sources']} ==
            {'michaelrolphone-cmyk/' + name for name in REPOSITORIES}, 'Unexpected source repositories')
    for source in mapping['sources']:
        require(all(re.fullmatch('[0-9a-f]{40}', source[key]) for key in
                    ('built_commit', 'public_tree_equivalent_commit', 'tree', 'bundle_prerequisite_commit')),
                'Unpinned source mapping')
        require(sha(custody[source['bundle_file']]) == source['bundle_sha256'], 'Original source bundle changed')
    return mapping


def hydrate(output, custody_path, build_inputs_path):
    require(not output.exists() and not output.is_symlink(), 'Reconstruction output must be new')
    custody = members(custody_path, CUSTODY_SHA)
    mapping = validate_mapping(custody)
    build_input_bytes = build_inputs_bytes(build_inputs_path)
    inputs = archive_members(build_input_bytes, BUILD_INPUTS_SHA)
    output.mkdir(parents=True)
    (output / 'source-custody.zip').write_bytes(custody_path.read_bytes())
    (output / 'reconstruction-inputs.zip').write_bytes(build_input_bytes)
    extract(custody, output / 'custody')
    extract(inputs, output / 'inputs')
    for source in mapping['sources']:
        name = source['repository'].split('/')[1]
        root = output / name
        fetch(root, source['repository'], source['bundle_prerequisite_commit'])
        bundle = output / 'custody' / source['bundle_file']
        run('git', '-C', root, 'bundle', 'verify', bundle)
        run('git', '-C', root, 'fetch', bundle, 'HEAD')
        run('git', '-C', root, 'checkout', '--detach', source['built_commit'])
        require(git(root, 'rev-parse', 'HEAD^{tree}') == source['tree'], 'Original source tree differs')
        require(not git(root, 'status', '--porcelain'), 'Restored original source is dirty')
    drivers = output / 'RiscRTE-Drivers'
    fetch(drivers, 'michaelrolphone-cmyk/RiscRTE-Drivers', DRIVERS_SHA)
    run('git', '-C', drivers, 'checkout', '--detach', DRIVERS_SHA)
    littlefs = output / 'RiscRTE/build/littlefs-source'
    fetch(littlefs, 'joltwallet/esp_littlefs', '41873c20fb5cdbcf28d7d6cc04e4bcb4a1305317')
    run('git', '-C', littlefs, 'checkout', '--detach', '41873c20fb5cdbcf28d7d6cc04e4bcb4a1305317')
    run('git', '-C', littlefs, 'submodule', 'update', '--init', '--recursive')
    print('Restored all five original source identities, public Drivers and pinned LittleFS:', output)


def native_environment(runtime):
    environment = dict(os.environ)
    core = Path(environment.get('PLATFORMIO_CORE_DIR', str(Path.home() / '.platformio'))).expanduser().absolute()
    package_prefixes = {str(core / 'packages'), str((core / 'packages').resolve())}
    # PlatformIO's multiple build_flags option adds this environment value to
    # the source flags. Repeating source flags changes DWARF producer strings.
    mapped = [environment['PLATFORMIO_BUILD_FLAGS']] if environment.get('PLATFORMIO_BUILD_FLAGS') else []
    for prefix in sorted(package_prefixes):
        mapped.append('-ffile-prefix-map=' + prefix + '=' + ACCEPTED_PACKAGE_PREFIX)
    environment['PLATFORMIO_BUILD_FLAGS'] = '\n'.join(mapped)
    print('Original native flags retained; Arduino diagnostic paths mapped to accepted prefix.', flush=True)
    return environment


def build(output, cc=None):
    custody = members(output / 'source-custody.zip', CUSTODY_SHA)
    mapping = validate_mapping(custody)
    for name, raw in members(output / 'reconstruction-inputs.zip', BUILD_INPUTS_SHA).items():
        require((output / 'inputs' / name).read_bytes() == raw, 'Extracted reconstruction input changed')
    for source in mapping['sources']:
        root = output / source['repository'].split('/')[1]
        require(git(root, 'rev-parse', 'HEAD') == source['built_commit'] and
                git(root, 'rev-parse', 'HEAD^{tree}') == source['tree'] and
                not git(root, 'status', '--porcelain', '--untracked-files=no'), 'Reconstructed source changed')
    runtime = output / 'RiscRTE'
    watch = output / 'RiscRTE-T-Watch-S3'
    if (runtime / 'build/appdata-initial').exists():
        # A cancelled native compile may leave this deterministic empty image.
        # Its original verifier rejects any changed bytes before reuse.
        run(sys.executable, '-c',
            "import sys;sys.path.insert(0,'scripts');from app_data_image import verify_initial;verify_initial('build/appdata-initial')",
            cwd=runtime)
    else:
        run(sys.executable, 'scripts/app_data_image.py', '--littlefs-source', 'build/littlefs-source/src/littlefs',
            '--output', 'build/appdata-initial', cwd=runtime)
    run(sys.executable, '-m', 'platformio', 'run', '-e', 'esp32s3-16mb-appdata-iq', '-j', '1',
        cwd=runtime, env=native_environment(runtime))
    source = git(runtime, 'rev-parse', 'HEAD')
    run(sys.executable, 'scripts/paired_candidate.py', '--app-data', '--radio-iq',
        '--app-data-image', 'build/appdata-initial', '--source-sha', source, cwd=runtime)
    if cc is None:
        core = Path(os.environ.get('PLATFORMIO_CORE_DIR', str(Path.home() / '.platformio')))
        cc = core / 'packages/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-gcc'
    require(Path(cc).is_file(), 'Pass --cc with the pinned Xtensa GCC 8.4.0 path')
    env = {**os.environ, 'TWATCH_CC': str(Path(cc).resolve())}
    apps = watch / 'dist/reconstructed-1.0.12-apps'
    run(sys.executable, 'scripts/build_current_apps.py', '--profile', 'runtime-features',
        '--system-apps', output / 'RiscRTE-System-Apps', '--utilities', output / 'RiscRTE-Utilities',
        '--productivity', output / 'RiscRTE-Productivity', '--runtime', runtime,
        '--drivers', output / 'RiscRTE-Drivers', '--motion-model', 'bma423', '--radio-model', 'selectable',
        '--baseline', output / 'inputs/rf-1.0.8-apps.zip', '--output', apps, cwd=watch, env=env)
    product = watch / 'dist/reconstructed-1.0.12-initial'
    run(sys.executable, 'scripts/build_runtime_features_watch_candidate.py', 'build', '--mode', 'initial',
        '--apps-dir', apps, '--runtime', runtime, '--native-dir', runtime / 'dist/esp32s3-16mb-appdata-iq',
        '--source-bundle', output / 'inputs/accepted-1.0.11', '--output', product, cwd=watch, env=env)
    image = product / 'twatch-s3-1.0.12-FULL-INITIAL-ERASES-DATA-bma423.bin'
    report = {'schema': 1, 'built_image_sha256': sha(image.read_bytes()), 'accepted_image_sha256': IMAGE_SHA,
              'byte_identical': sha(image.read_bytes()) == IMAGE_SHA, 'release_modified': False,
              'native_rebuilt': True, 'app_and_provider_sources_rebuilt': True,
              'preserving_update_retested': False}
    accepted = json.loads(custody['proof/runtime-features-watch-build-proof.json'])
    fresh = json.loads((product / 'runtime-features-watch-build-proof.json').read_text())
    report['native_firmware_sha256'] = sha((runtime / 'dist/esp32s3-16mb-appdata-iq/firmware.bin').read_bytes())
    report['accepted_native_firmware_sha256'] = accepted['native_custody']['assets']['firmware.bin']['sha256']
    report['changed_store_files'] = sorted(name for name in set(accepted['files']) | set(fresh['files'])
        if accepted['files'].get(name) != fresh['files'].get(name))
    report['package_path_mapping'] = ACCEPTED_PACKAGE_PREFIX
    (output / 'reconstruction-result.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, indent=2, sort_keys=True))
    require(report['byte_identical'], 'Reconstructed full image differs from the accepted bytes; inspect fresh evidence')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('hydrate', 'build'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source-custody', type=Path, default=Path('source-custody.zip'))
    inputs = p.add_mutually_exclusive_group()
    inputs.add_argument('--build-inputs', type=Path, default=Path('reconstruction-inputs.zip'))
    inputs.add_argument('--build-inputs-gzip-parts', type=Path, nargs=2, metavar=('PART1', 'PART2'))
    p.add_argument('--cc', type=Path)
    a = p.parse_args()
    if a.action == 'hydrate':
        build_inputs = tuple(path.resolve() for path in a.build_inputs_gzip_parts) if a.build_inputs_gzip_parts else a.build_inputs.resolve()
        hydrate(a.output.resolve(), a.source_custody.resolve(), build_inputs)
    else:
        build(a.output.resolve(), a.cc)


if __name__ == '__main__':
    main()
