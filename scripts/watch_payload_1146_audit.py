#!/usr/bin/env python3
"""Read-only 1.1.46 source/metadata audit; never generates an installable payload."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/watch-payload-admission-1.1.46'
REPOSITORY = 'michaelrolphone-cmyk/RiscRTE-T-Watch-S3'
BASE = '81dbde86969615f7378cc03c5800960a9092e076'
PRODUCER = 'ab9ff33975680c5bb8d9a2e7ed346d0300732a4e'
RUNTIME = '48229bd1593a2e24e95bf4537b495ee615990fd3'
TAG = 'test-provisioning-1.1.46'
RELEASE_ID = 415753487
FEED_SHA = '2f08c10587344d3eb2ae07967a990ec1102719c9298582daa60037bd470549c3'
STORE_SHA = 'e50d26000dc0366be61abbf480cd39ee98323ea5ef489536baf0cf7c4097b126'
FIRMWARE_SHA = 'cd8f7f51d9c604e4f3b12b5f54dcc83817b812baa973b5862321a94e951f0034'
FACTORY_SHA = 'e132a6276cd444cd41482ecfcc2043296b2acf02ef882acc83ba1af4c76edff6'
SOURCE_IDS = {'feed', 'producer_pins', 'producer_profile', 'native_profile',
              'producer_feed', 'producer_package', 'feed_builder', 'payload_contract',
              'payload_schema', 'serial_storage', 'serial_selectors', 'package_volume',
              'mount_isolation', 'appdata_files', 'serial_growth', 'serial_reserve',
              'partitions', 'store_files', 'bank_store', 'provision_profile'}
ADMISSION = {'generic_pair_available': False, 'rtef1_core_destination': None,
             'accepted_generic_consumer': None, 'accepted_write_budget': None,
             'accepted_hardware_revisions': None, 'trusted_release_context': None,
             'payload_manifest_emitted': False, 'hardware_qualified': False}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate JSON key: ' + key)
        value[key] = item
    return value


def decode(raw):
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite JSON')))


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def record(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def exact(raw, expected, label):
    require(record(raw) == {k: expected[k] for k in ('bytes', 'sha256')}, 'byte identity differs: ' + label)


def bounded_read(path):
    path = Path(path)
    require(not path.is_symlink() and path.is_file(), 'regular input required')
    raw = path.read_bytes()
    require(0 < len(raw) <= 512 * 1024, 'input exceeds source/metadata bound')
    return raw


def fetch(url):
    require(url.startswith(('https://raw.githubusercontent.com/',
                            'https://api.github.com/repos/')), 'public GitHub URL required')
    request = urllib.request.Request(url, headers={'User-Agent': 'TWatch-source-admission-audit',
                                                   'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        require(response.geturl().startswith(('https://raw.githubusercontent.com/',
                                               'https://api.github.com/repos/')), 'unexpected source redirect')
        raw = response.read(512 * 1024 + 1)
    require(0 < len(raw) <= 512 * 1024, 'remote source/metadata bound')
    return raw


def check_lock(lock):
    require(lock['schema'] == 'riscrte.watch-source-admission-audit/1' and
            lock['source_only'] is True and lock['base_commit'] == BASE, 'audit scope differs')
    require(lock['release'] == {'repository': REPOSITORY, 'id': RELEASE_ID, 'tag': TAG,
            'producer': PRODUCER, 'runtime_commit': RUNTIME, 'runtime_version': '0.4.11'}, 'release pin differs')
    require(lock['admission'] == ADMISSION, 'unsupported admission claim')
    require(lock['expected_inventory'] == {'files': 125, 'elf': 61, 'json': 64, 'bytes': 4958853},
            'inventory totals differ')
    sources = lock['sources']
    require(len(sources) == len(SOURCE_IDS) and {r['id'] for r in sources} == SOURCE_IDS,
            'complete source closure required')
    for row in sources:
        require(re.fullmatch(r'[0-9a-f]{40}', row['commit']) is not None and
                re.fullmatch(r'[0-9a-f]{40}', row['git_blob_sha1']) is not None and
                re.fullmatch(r'[0-9a-f]{64}', row['sha256']) is not None, 'source digest malformed')
        expected = (PRODUCER if row['id'].startswith('producer_') or row['id'] == 'native_profile'
                    else 'c2ea463a0bff968ce38e2a270aedfae7c49fefb4' if row['id'] == 'feed'
                    else 'bb0cadf3cec3445a64e11513b47b2676f3fdd92d' if row['id'] == 'feed_builder'
                    else '908355b0509907c05a6dc47a1ccc8e078d6e23b0' if row['id'].startswith('payload_')
                    else RUNTIME)
        require(row['commit'] == expected, 'source revision differs: ' + row['id'])
        require(row['repository'] in {REPOSITORY, 'michaelrolphone-cmyk/RiscRTE',
                                      'michaelrolphone-cmyk/RiscRTE-System-Apps'}, 'unexpected repository')
        require(row['path'] and all(p not in ('', '.', '..') for p in row['path'].split('/')),
                'unsafe source path')
        require(row['url'] == f"https://github.com/{row['repository']}/blob/{row['commit']}/{row['path']}",
                'source URL does not bind exact revision')


def read_sources(lock, cache, online=False):
    result = {}
    for row in lock['sources']:
        path = Path(cache) / row['id']
        if online:
            raw = fetch(f"https://raw.githubusercontent.com/{row['repository']}/{row['commit']}/{row['path']}")
        else:
            raw = bounded_read(path)
        exact(raw, row, row['id'])
        require(blob(raw) == row['git_blob_sha1'], 'Git source object differs: ' + row['id'])
        if online:
            path.parent.mkdir(parents=True, exist_ok=True)
            require(not path.is_symlink(), 'source cache symlink refused')
            path.write_bytes(raw)
        result[row['id']] = raw
    return result


def check_sources(source):
    # These readable anchors explain the hash-pinned source facts. They are not
    # claimed to be a compiler, runtime test, or general semantic proof.
    anchors = {
        'serial_storage': ['{2,"Serial files",&privateClient,true}', 'configure("/appdata/.serial-files")'],
        'serial_selectors': ['#define RISC_NATIVE_SERIAL_BOOT_FILES 0', '#define RISC_NATIVE_SERIAL_SD 0'],
        'native_profile': ['RISC_NATIVE_SERIAL_FILES=1', 'RISC_NATIVE_SERIAL_APPDATA_FILES=1',
                           'partitions-paired-appdata-expanded.csv'],
        'producer_profile': ['native-idf61.cmake', 'RISC_NATIVE_PACKAGE_VOLUME=1'],
        'package_volume': ['configure("/appdata/.packages")'],
        'mount_isolation': ['access==Access::Packages?under(p,Packages)',
                            'access==Access::SerialFiles?under(p,SerialFiles):!under(p,SerialFiles)&&'],
        'appdata_files': ['"%s/n%08lx"'],
        'serial_reserve': ['ReservedBytes=139264'],
        'serial_growth': ['free>=ReservedBytes+4096', 'growth<=free-ReservedBytes-4096'],
        'partitions': ['appdata,data,0x41,0x270000,0x80000'],
        'producer_feed': ["len(core['profile']['files'])==125 and not core['mirrors']",
                          "feed['apps']==[] and feed['profiles']=={'core':[]}"],
        'producer_package': ["result['installation']", "'internal_volume_instance': 0",
                             "require(not any(r.get('image_source')", 'T-Watch must remain internal-only'],
        'feed_builder': ["helpers.read_image(raw, partition) == files", 'p.verify_inventory(inventory, files)'],
        'store_files': ['count==p.count', 'ok=verify(p.files[i])'],
        'bank_store': ['Non-policy child apps and unselected driver files are still native code;',
                       'prepare/inspect never map modules, issue grants, invoke providers or touch'],
        'payload_contract': ['a manifest cannot grant itself storage authority',
                             'RTEF1 has no free-space query'],
    }
    for key, needles in anchors.items():
        text = source[key].decode()
        require(all(n in text for n in needles), 'source fact differs: ' + key)
    profile = source['native_profile'].decode()
    require('RISC_NATIVE_SERIAL_SD=1' not in profile and 'RISC_NATIVE_SERIAL_BOOT_FILES=1' not in profile,
            'unexpected serial provider selection')
    pins = decode(source['producer_pins'])
    require(pins['runtime_revision'] == RUNTIME and pins['runtime_version'] == '0.4.11'
            and pins['release_tag'] == TAG and pins['default_bytes'] == 554744, 'producer lineage differs')
    schema = decode(source['payload_schema'])['properties']['payload']['properties']
    require(schema['volumes']['minItems'] == schema['files']['minItems'] == 1 and
            schema['totals']['properties']['file_count']['minimum'] == 1, 'nonempty payload contract differs')


def check_feed(feed):
    require(set(feed) == {'apps', 'boot_profiles', 'product', 'profiles', 'schema', 'version'}, 'feed fields differ')
    require(feed['schema'] == 'riscrte.native-packages' and type(feed['version']) is int and
            feed['version'] == 1 and feed['product'] == 'twatch-s3', 'feed identity differs')
    require(feed['apps'] == [] and feed['profiles'] == {'core': []}, 'dynamic catalog scope differs')
    require(set(feed['boot_profiles']) == {'core'}, 'core profile missing or extra')
    core = feed['boot_profiles']['core']
    require(set(core) == {'mirrors', 'native', 'profile', 'time'} and core['mirrors'] == [], 'core fields or mirrors differ')
    require(core['native'] == {'firmware_sha256': FIRMWARE_SHA, 'firmware_size': 1624560,
            'layout': 'riscrte-paired-appdata-v3', 'runtime_version': '0.4.11', 'store_abi': 3}, 'native binding differs')
    profile = core['profile']
    require(set(profile) == {'files', 'image', 'schema', 'schema_version'} and
            profile['schema'] == 'riscrte.provisioning' and type(profile['schema_version']) is int and
            profile['schema_version'] == 4, 'core profile shape differs')
    image_url = f'https://github.com/{REPOSITORY}/releases/download/{TAG}/bootfs-{STORE_SHA}.bin'
    require(profile['image'] == {'bytes': 5570560, 'sha256': STORE_SHA, 'url': image_url}, 'store binding differs')
    require(core['time'] == {'schema': 'riscrte.sntp', 'schema_version': 1,
                             'servers': ['time.cloudflare.com']}, 'time input differs')
    files = profile['files']
    require(isinstance(files, list) and len(files) == 125, 'complete 125-file inventory required')
    names = []
    total = 0
    kinds = {'elf': 0, 'json': 0}
    for row in files:
        require(isinstance(row, list) and len(row) == 3, 'inventory row fields')
        path, size, digest = row
        require(isinstance(path, str) and 0 < len(path.encode()) <= 30 and
                all(p not in ('', '.', '..') and re.fullmatch(r'[A-Za-z0-9_.-]+', p)
                    for p in path.split('/')), 'unsafe store path')
        require(path != '.provision-sha256' and path not in names and
                not any(path.startswith(n + '/') or n.startswith(path + '/') for n in names),
                'duplicate, overlapping or reserved path')
        require(type(size) is int and 1 <= size <= 8 * 1024 * 1024, 'file size bounds')
        require(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest), 'file digest malformed')
        kind = path.rsplit('.', 1)[-1]
        require(kind in kinds, 'unaccounted file kind')
        kinds[kind] += 1
        total += size
        names.append(path)
    require(names == sorted(names, key=lambda n: n.encode()), 'inventory order differs')
    require(kinds == {'elf': 61, 'json': 64} and total == 4958853, 'inventory totals differ')
    require({'boot.json', 'board.json', 'cohort.json', 'default.elf'} <= set(names), 'core bootstrap incomplete')
    require(next(row[1] for row in files if row[0] == 'default.elf') == 554744, 'default size differs')
    return files


def metadata(api):
    result = {k: api[k] for k in ('id', 'tag_name', 'target_commitish', 'draft', 'prerelease')}
    result['assets'] = [{k: row[k] for k in ('name', 'size', 'digest', 'browser_download_url')}
                        for row in sorted(api['assets'], key=lambda r: r['name'])]
    result['evidence'] = 'GitHub release API metadata, not downloaded binary verification'
    return result


def check_metadata(value):
    require(value['id'] == RELEASE_ID and type(value['id']) is int and
            value['tag_name'] == TAG and value['target_commitish'] == PRODUCER and value['draft'] is False,
            'release metadata identity differs')
    rows = value['assets']
    require(len(rows) == 19 and len({r['name'] for r in rows}) == 19, 'release asset inventory differs')
    assets = {r['name']: r for r in rows}
    for name, size, digest in [('native-packages-v1.json', 12674, FEED_SHA),
            ('store.bin', 5570560, STORE_SHA), ('bootfs-' + STORE_SHA + '.bin', 5570560, STORE_SHA),
            ('firmware.bin', 1624560, FIRMWARE_SHA),
            ('TWatch-1.1.46-Provisioning-factory-erases-data-0x0.bin', 16777216, FACTORY_SHA)]:
        row = assets[name]
        require(row['size'] == size and row['digest'] == 'sha256:' + digest, 'release artifact metadata differs: ' + name)
    for row in rows:
        require(type(row['size']) is int and row['size'] > 0 and
                isinstance(row['digest'], str) and re.fullmatch(r'sha256:[0-9a-f]{64}', row['digest']),
                'asset metadata size or digest malformed')
        require(row['browser_download_url'] == f"https://github.com/{REPOSITORY}/releases/download/{TAG}/{row['name']}",
                'release asset URL differs')


def make_matrix(files):
    return {'schema': 'riscrte.watch-core-consumer-audit/1', 'release_tag': TAG,
            'evidence_scope': 'declared file identities verified against pinned feed and source; binaries not downloaded',
            'not_an_installable_payload': True, 'rows': [
                {'path': path, 'bytes': size, 'sha256': digest, 'format': path.rsplit('.', 1)[-1],
                 'classification': 'firmware-owned-internal-store',
                 'consumer': 'complete-core-profile-verification-and-paired-boot-store',
                 'evidence': ['feed', 'producer_feed', 'producer_package', 'feed_builder', 'store_files', 'bank_store'],
                 'feed_pointer': f'/boot_profiles/core/profile/files/{index}',
                 'rtef1_destination': None, 'execution_verified': False}
                for index, (path, size, digest) in enumerate(files)]}


def matrix_markdown(matrix):
    lines = ['# Complete 1.1.46 core inventory / consumer matrix', '',
             'All 125 rows are firmware-owned internal-store files. Consumer C is the complete core-profile',
             'readback/verification and paired boot-store path documented by source evidence below.',
             'Destination NONE means no admitted RTEF1 destination, not missing bootstrap.',
             'ELF is a file-format classification, not proof that the file executes.',
             'Sizes/hashes below are declarations from the exact pinned feed, not newly hashed binaries.', '',
             'Evidence: source-lock.json IDs feed, producer_feed, producer_package, feed_builder, store_files, bank_store.', '',
             '| Core path | Bytes | Declared SHA256 | Format | Consumer | RTEF1 destination |',
             '| --- | ---: | --- | --- | --- | --- |']
    lines.extend(f"| {r['path']} | {r['bytes']} | {r['sha256']} | {r['format']} | C | NONE |" for r in matrix['rows'])
    return ('\n'.join(lines) + '\n').encode()


def check_git_scope(lock):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args])
    allowed = {'scripts/watch_payload_1146_audit.py', 'scripts/test_watch_payload_1146_audit.py',
               '.github/workflows/watch-payload-1146-audit.yml'}
    allowed.update('docs/watch-payload-admission-1.1.46/' + name for name in
                   ('README.md', 'source-lock.json', 'core-feed.json', 'release-metadata.json',
                    'inventory-consumers.json', 'inventory-consumers.md'))
    changed = git('diff', '--name-only', BASE, 'HEAD').decode().splitlines()
    require(changed and all(p in allowed for p in changed),
            'source-only diff scope exceeded')
    require(not git('diff', '--name-only', '--diff-filter=DMR', BASE, 'HEAD'), 'existing file modified, deleted or renamed')
    for row in lock['historical_files_unchanged']:
        require(blob(git('show', 'HEAD:' + row['path'])) == row['sha'], 'historical audit changed')
    return git('rev-parse', 'HEAD').decode().strip()


def require_pair():
    raise ValueError('No admitted nonempty core-file RTEF1 destination/consumer or trusted release context; generic pair rejected')


def audit(docs=DOCS, cache=None, online=False, git_scope=False, write_matrix=False):
    docs = Path(docs)
    lock = decode(bounded_read(docs / 'source-lock.json'))
    check_lock(lock)
    snapshots = {}
    for name in ('core-feed.json', 'release-metadata.json'):
        raw = bounded_read(docs / name)
        exact(raw, lock['snapshots'][name], name)
        snapshots[name] = raw
    require(record(snapshots['core-feed.json']) == {'bytes': 12674, 'sha256': FEED_SHA}, 'exact release feed differs')
    files = check_feed(decode(snapshots['core-feed.json']))
    release = decode(snapshots['release-metadata.json'])
    check_metadata(release)
    source = read_sources(lock, cache or docs / '.source-cache', online)
    require(source['feed'] == snapshots['core-feed.json'], 'published feed snapshot differs')
    check_sources(source)
    if online:
        current = metadata(decode(fetch(f'https://api.github.com/repos/{REPOSITORY}/releases/{RELEASE_ID}')))
        require(current == release, 'live public release metadata differs from retained snapshot')
    matrix = make_matrix(files)
    expected = {'inventory-consumers.json': encoded(matrix), 'inventory-consumers.md': matrix_markdown(matrix)}
    for name, raw in expected.items():
        if write_matrix:
            (docs / name).write_bytes(raw)
        else:
            require(bounded_read(docs / name) == raw, 'derived matrix differs: ' + name)
    head = check_git_scope(lock) if git_scope else None
    return {'schema': 'riscrte.watch-source-audit-result/1', 'audit_status': 'source-and-metadata-checks-passed',
            'checked_source_head': head, 'release_tag': TAG, 'producer_commit': PRODUCER,
            'runtime_commit': RUNTIME, 'inventory': lock['expected_inventory'],
            'source_files_verified': len(source), 'source_online_readback': online,
            'release_metadata_online_readback': online, 'release_binary_bytes_downloaded': 0,
            'matrix': {name: record(raw) for name, raw in expected.items()},
            'admission': ADMISSION, 'generic_pair_status': 'rejected',
            'capacity_observations': {'whole_appdata_partition_bytes': 524288,
                'default_elf_declared_bytes': 554744, 'serial_reserved_bytes': 139264,
                'serial_additional_guard_bytes': 4096, 'installer_write_budget': None},
            'native_build_performed': False, 'target_instructions_executed': False,
            'factory_preservation_verified': False, 'hardware_tested': False,
            'claim_limits': ['No fresh release-binary hash/readback, extraction or native-loader rerun.',
                             'No installable manifest/container, destination alias, storage implementation or publication.',
                             'Source constants are observations, not an admitted installer budget.',
                             'Factory bootstrap is not a preserving generic serial update.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-cache', type=Path)
    parser.add_argument('--fetch', action='store_true', help='Read only pinned public GitHub text and release metadata')
    parser.add_argument('--git-scope', action='store_true')
    parser.add_argument('--write-matrix', action='store_true', help='Regenerate audit matrices, never a payload')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-paired', action='store_true', help='Must reject this release; emits only factual audit JSON')
    args = parser.parse_args()
    try:
        result = audit(cache=args.source_cache, online=args.fetch, git_scope=args.git_scope,
                       write_matrix=args.write_matrix)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded(result))
        if args.require_paired:
            require_pair()
        print('125 files; 20 pinned sources; source/metadata audit passed; generic serial pair REJECTED.')
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('Audit rejected: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
