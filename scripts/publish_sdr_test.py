#!/usr/bin/env python3
"""Manual-only, frozen-CI publication of the two distinct SDR update stages.

No build, physical-device access, device attestation or automatic stage
advancement is performed. The default product manifest remains frozen.
"""
import argparse
import base64
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile

import current_cohort as cohort
import publish_watch_product as pub
from read_only_spiffs import read_image
from watch_release_index import REPOSITORY, require, update_index, validate_record

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / 'release/sdr-test-acceptance.json'
BASELINE = json.loads((ROOT / 'apps/sdr-upgrade-baseline.json').read_text())
RUNTIME = '0a4f3d18c5d830d32678092fa99284810334b485'
STAGES = {'native': ('1.0.3', 'release-index.stage1-native.json'),
          'cohort': ('1.0.4', 'release-index.stage2-cohort.json')}
NOTICE = ('Experimental SDR test, not hardware-qualified. Installed Watch 1.0.2 must use '
          'built-in Firmware Update in two separately published stages: native bridge 1.0.3, '
          'then cohort 1.0.4 only after the operator confirms the bridge restarted with a '
          'healthy Clock and retained data. OTA payloads preserve NVS/app-data; software tests '
          'are not physical-device attestation. Full twatch-s3-launcher images are destructive '
          'INITIAL PROVISIONING ONLY: never flash these to upgrade an installed Watch. '
          'See INSTALL.txt. No device operation is performed by publication.')


def exact_hex(value, length):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value)


def decode(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique)


def validate_acceptance(a):
    require(isinstance(a, dict) and type(a.get('schema')) is int and a['schema'] == 1 and
            a.get('repository') == REPOSITORY, 'Wrong SDR acceptance identity')
    require(exact_hex(a.get('source_sha'), 40) and exact_hex(a.get('sha256'), 64),
            'Exact accepted source and artifact hash required')
    require(all(type(a.get(k)) is int and a[k] > 0 for k in ('run_id', 'run_attempt', 'artifact_id')),
            'Exact accepted CI run, attempt and artifact required')
    require(a.get('name') == 'twatch-sdr-upgrade-' + a['source_sha'], 'Wrong accepted artifact name')
    require(a.get('base_index_commit') == BASELINE['index_source'], 'Wrong frozen baseline index commit')
    base = a.get('base_index', {})
    firmware = validate_record('firmware', base.get('firmware'))
    require(base.get('schema') == 1 and firmware['version'] == '1.0.2' and
            firmware['sha256'] == BASELINE['release_bin_sha256'] and firmware['size'] == 0x1000000,
            'Frozen 1.0.2 predecessor differs')
    return a


def verify_ci(a):
    """Bind one immutable artifact to the successful accepted workflow attempt."""
    run = pub.api(f'repos/{REPOSITORY}/actions/runs/{a["run_id"]}/attempts/{a["run_attempt"]}')
    require(run.get('id') == a['run_id'] and run.get('run_attempt') == a['run_attempt'] and
            run.get('head_sha') == a['source_sha'] and run.get('status') == 'completed' and
            run.get('conclusion') == 'success' and run.get('path') == '.github/workflows/drivers.yml' and
            run.get('repository', {}).get('full_name') == REPOSITORY, 'Accepted CI run identity/status differs')
    item = pub.api(f'repos/{REPOSITORY}/actions/artifacts/{a["artifact_id"]}')
    require(item.get('id') == a['artifact_id'] and item.get('name') == a['name'] and
            item.get('expired') is False and item.get('workflow_run', {}).get('id') == a['run_id'] and
            item['workflow_run'].get('head_sha') == a['source_sha'], 'Accepted CI artifact identity differs')
    time = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(time(run['run_started_at']) <= time(item['created_at']) <= time(run['updated_at']),
            'Artifact belongs to another CI attempt')
    require(item.get('digest') in (None, 'sha256:' + a['sha256']), 'CI artifact digest differs')


def download(a):
    verify_ci(a)
    data = pub.gh('api', f'repos/{REPOSITORY}/actions/artifacts/{a["artifact_id"]}/zip')
    require(pub.sha(data) == a['sha256'], 'Accepted CI ZIP hash differs')
    return data


def verify_bundle(a, raw):
    """Reject mixed payloads/catalogs/proofs even when the outer ZIP was reviewed."""
    validate_acceptance(a)
    require(pub.sha(raw) == a['sha256'], 'Accepted CI ZIP hash differs')
    with pub.checked_zip(raw) as z:
        files = {n: z.read(n) for n in z.namelist() if not n.endswith('/')}
    get = lambda name: files['sdr-upgrade/' + name]
    proof = decode(get('sdr-build-proof.json'))
    require(proof['watch_source'] == a['source_sha'] and
            proof['source_release_sha256'] == BASELINE['release_bin_sha256'] and
            proof['source_cohort']['version'] == '1.0.2' and
            proof['source_cohort']['source_revision'] == BASELINE['source_sha'], 'Mixed source/baseline proof')
    require(proof['configuration']['sources']['runtime']['commit'] == RUNTIME and
            proof['configuration']['app_versions']['springboard'] == '1.4.10', 'Wrong final launcher/native configuration')
    for key in ('both_catalogs_accepted_by_installed_provider', 'monotonic_catalog_stages',
                'initial_image_is_destructive', 'ordinary_payloads_exclude_nvs_appdata_bootloader_partitions'):
        require(proof.get(key) is True, 'Missing SDR build gate: ' + key)
    indexes, releases = {}, {}
    previous = a['base_index']
    for stage, (version, index_name) in STAGES.items():
        tag = 'firmware-v' + version
        index = decode(get(index_name))
        record = validate_record('firmware', index['firmware'])
        require(record['version'] == version and record['source_sha'] == a['source_sha'] and
                record.get('hardware_qualified') is False, 'Wrong stage source/version/qualification')
        require(index == update_index(previous, 'firmware', record),
                'Stage must advance only firmware; existing catalog rows are immutable')
        previous = index
        assets = {name.removeprefix('sdr-upgrade/' + tag + '/'): data for name, data in files.items()
                  if name.startswith('sdr-upgrade/' + tag + '/')}
        ota = record['ota']
        require(set(assets) == {record['asset'], ota['asset'], 'release-record.json',
                               'radio-iq-proof.json', 'LICENSES.zip', 'SHA256SUMS'}, 'Stage asset inventory differs')
        require(decode(assets['release-record.json']) == record, 'Mixed release record')
        sums = ''.join(f'{pub.sha(data)}  {name}\n' for name, data in sorted(assets.items()) if name != 'SHA256SUMS')
        require(assets['SHA256SUMS'] == sums.encode(), 'Stage checksums differ')
        for row in (record, ota):
            payload = assets[row['asset']]
            require(type(row['size']) is int and len(payload) == row['size'] and
                    pub.sha(payload) == row['sha256'], 'Stage payload hash/size differs')
        require(ota['url'] == f'https://github.com/{REPOSITORY}/releases/download/{tag}/{ota["asset"]}' and
                ota['runtime_version'] == '0.1.34' and ota['layout'] == cohort.LAYOUT and
                type(ota['store_abi']) is int and ota['store_abi'] == 2, 'Wrong immutable OTA identity')
        require(len(assets[record['asset']]) == 0x1000000, 'Initial-only image size differs')
        indexes[stage], releases[stage] = index, assets
    native = indexes['native']['firmware']; final = indexes['cohort']['firmware']
    fw = releases['native'][native['ota']['asset']]
    require(native['ota']['kind'] == 'runtime-image' and native['ota']['asset'] == 'riscrte-runtime-0.1.34.bin' and
            32 <= len(fw) <= cohort.NATIVE_SIZE and fw[0] == 0xe9 and
            pub.sha(fw) == proof['native_sha256'], 'Wrong native-only bridge payload')
    require(native['component_versions'] == {**a['base_index']['firmware']['component_versions'], 'runtime': '0.1.34'},
            'Native stage changes existing app versions')
    require(final['component_versions'] == {**proof['configuration']['app_versions'], 'runtime': '0.1.34'},
            'Final component versions differ')
    payload = releases['cohort'][final['ota']['asset']]
    require(len(payload) == len(fw) + cohort.STORE_SIZE and payload[:len(fw)] == fw,
            'Paired payload must contain only the exact native image and boot store')
    store = payload[len(fw):]
    members = read_image(store, cohort.STORE_SIZE)
    identity = cohort.parse(members['cohort.json'])
    cohort.verify(identity, fw, version='1.0.4', runtime_version='0.1.34', source_revision=a['source_sha'])
    _, expected_ota = cohort.package(identity, fw, store)
    require(final['ota'] == expected_ota and proof['target_cohort'] == identity and
            proof['cohort_sha256'] == pub.sha(payload) and proof['cohort_bytes'] == len(payload), 'Mixed cohort identity/payload')
    require({n: {'size_bytes': len(b), 'sha256': pub.sha(b)} for n, b in members.items()} == proof['files'],
            'Store members differ from build proof')
    for stage, image_digest in (('native', 'bridge_initial_image_sha256'), ('cohort', 'initial_image_sha256')):
        record = indexes[stage]['firmware']; full = releases[stage][record['asset']]
        require(pub.sha(full) == proof[image_digest] and full[0x10000:0x10000 + len(fw)] == fw,
                'Initial image native/source differs')
        if stage == 'native':
            require(record['native_bridge'] == {'retained_cohort_version': '1.0.2',
                    'retained_store_sha256': pub.sha(full[0x2f0000:0x800000])}, 'Bridge store anchor differs')
            old_members = read_image(full[0x2f0000:0x800000], cohort.STORE_SIZE)
            require(cohort.parse(old_members['cohort.json']) == proof['source_cohort'], 'Bridge relabels old cohort')
            require(pub.sha(full[0x2f0000:0x800000]) == a['base_index']['firmware']['ota']['store_sha256'],
                    'Native bridge must retain the frozen 1.0.2 store byte for byte')
        else:
            require(full[0x2f0000:0x800000] == store, 'Initial image and OTA store differ')
    new_members = {'waterfall.elf', 'waterfall.json', 's3-radio-iq/driver.elf', 's3-radio-iq/manifest.json'}
    changed_members = {'boot.json', 'cohort.json', 'springboard.elf', 'springboard.json'}
    require(set(members) == set(old_members) | new_members and not (set(old_members) & new_members),
            'Unexpected new/deleted SDR store member')
    require(all(members[n] == data for n, data in old_members.items() if n not in changed_members),
            'Existing app/provider/store bytes changed outside reviewed SDR scope')
    old_app = decode(old_members['springboard.json']); new_app = decode(members['springboard.json'])
    require(old_app.pop('version') == '1.4.9' and new_app.pop('version') == '1.4.10' and old_app == new_app,
            'Springboard authority changed')
    boot = decode(members['boot.json']); migration = boot.pop('cohort_migration')
    require(migration == {'schema': 1, 'from': {'product': 'twatch-s3', 'version': '1.0.2',
            'source_revision': BASELINE['source_sha']}, 'to': {'product': 'twatch-s3', 'version': '1.0.4'},
            'shared_key_value': [{'application_id': 'waterfall', 'api': 1, 'namespace': 1}]},
            'SDR migration authority differs')
    boot['app_capabilities'] = [x for x in boot['app_capabilities'] if x['manifest'] != 'waterfall.json']
    boot['drivers'] = [x for x in boot['drivers'] if x['manifest'] != 's3-radio-iq/manifest.json']
    require(boot == decode(old_members['boot.json']), 'Existing boot authority changed')
    require(releases['native']['radio-iq-proof.json'] == releases['cohort']['radio-iq-proof.json'] and
            releases['native']['LICENSES.zip'] == releases['cohort']['LICENSES.zip'], 'Mixed release proofs/licenses')
    launcher = decode(files['current-launcher-catalog-proof.json'])
    require(launcher['watch_source'] == a['source_sha'] and launcher['entries'] == 18 and
            launcher['system_source'] == proof['configuration']['sources']['system-apps']['commit'] and
            [t['sanitized'] for t in launcher['tests']] == [False, True], 'Missing final 18-entry launcher proof')
    for name in ('sdr-upgrade-test', 'sdr-upgrade-test-san'):
        test = decode(files[name + '/upgrade-proof.json'])
        require(test['native_candidate'] == RUNTIME and test['native_sha256'] == pub.sha(fw) and
                test['cohort_sha256'] == pub.sha(payload) and test['released_bin_sha256'] == BASELINE['release_bin_sha256'] and
                test['direct_old_cohort_rejected'] is True and test['staged_graph_admission']['cohort_validated'] is True and
                test['physical_flash_tls_spiffs_and_target_instructions_executed'] is False and
                len(test['transactions']) == 4 and
                sorted(t['payload_bytes'] for t in test['transactions']) == [len(fw), len(fw), len(payload), len(payload)] and
                all(t['native_bytes'] == len(fw) and t['nvs_appdata_preserved'] is True and
                t['previous_pair_preserved'] is True and t['target_executed'] is False for t in test['transactions']),
                'Missing/mixed two-stage preservation and rollback proof')
    return indexes, releases, get('INSTALL.txt')


def confirmation(a, predecessor):
    return ('I confirm the installed Watch completed native bridge 1.0.3 through Firmware Update, '
            'restarted with a healthy Clock and retained data; proceed to cohort 1.0.4. '
            f'Artifact SHA256 {a["sha256"]}; stage-1 index {predecessor}.')


def check_transition(a, indexes, stage, predecessor, parent, current, operator_confirmation=''):
    require(exact_hex(predecessor, 40) and parent == predecessor, 'Wrong live index predecessor commit')
    expected = a['base_index'] if stage == 'native' else indexes['native']
    if stage == 'native':
        require(predecessor == a['base_index_commit'], 'Stage 1 requires frozen 1.0.2 predecessor')
        require(not operator_confirmation, 'Stage 1 must not claim bridge health before installation')
    else:
        require(operator_confirmation == confirmation(a, predecessor),
                'Stage 2 requires explicit operator-confirmed healthy native bridge restart; no device attestation is inferred')
    require(current == expected, 'Wrong live predecessor index; same-version rewrites and skipped stages are forbidden')
    require(update_index(current, 'firmware', indexes[stage]['firmware']) == indexes[stage], 'Non-monotonic stage transition')


def stage_releases(a, releases, install, output):
    output.mkdir(parents=True, exist_ok=True)
    result = {}
    for stage, (version, _) in STAGES.items():
        assets = dict(releases[stage]); assets.pop('SHA256SUMS')
        assets.update({'INSTALL.txt': install, 'PUBLICATION.txt': (NOTICE + '\n').encode()})
        result[stage] = pub.write_release(output, decode(assets['release-record.json']), assets, a['source_sha'], False)
    return result


def publish(a, raw, stage, predecessor, operator_confirmation='', *, mutate=False):
    indexes, assets, install = verify_bundle(a, raw)
    verify_ci(a)
    source = pub.command('git', 'rev-parse', 'HEAD').decode().strip()
    require(not pub.command('git', 'status', '--porcelain', '--untracked-files=no').strip(), 'Publisher source dirty')
    require(pub.command('git', 'show', 'HEAD:release/sdr-test-acceptance.json') == ACCEPTANCE.read_bytes() and
            decode(ACCEPTANCE.read_bytes()) == a, 'Acceptance must be committed at publisher source')
    pub.verify_watch_ancestry(a['source_sha'], source)
    require(pub.command('git', 'show', a['source_sha'] + ':release/product.json') == pub.CONFIG.read_bytes(),
            'Frozen 1.0.2 product manifest changed')
    if mutate:
        repo = pub.api('repos/' + REPOSITORY)
        require(os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch' and
                os.environ.get('GITHUB_REPOSITORY') == REPOSITORY and
                os.environ.get('GITHUB_REF') == 'refs/heads/' + repo['default_branch'] and
                pub.api(f'repos/{REPOSITORY}/commits/{repo["default_branch"]}')['sha'] == source,
                'SDR publication requires explicit manual dispatch at current default source')
    parent, current = pub.current_release_index()
    check_transition(a, indexes, stage, predecessor, parent, current, operator_confirmation)
    with tempfile.TemporaryDirectory(prefix='sdr-publish-') as tmp:
        output = Path(tmp); releases = stage_releases(a, assets, install, output)
        if stage == 'cohort':
            bridge = pub.release_by_tag('firmware-v1.0.3')
            require(bridge and not bridge['draft'], 'Native bridge must already be published')
            pub.release_preflight([releases['native']], output, prerelease=True)
        pub.release_preflight([releases[stage]], output, prerelease=True)
        if mutate:
            # A changed catalog fails closed both before asset publication and at
            # the existing non-force index push. It can never silently rebase.
            parent2, current2 = pub.current_release_index()
            check_transition(a, indexes, stage, predecessor, parent2, current2, operator_confirmation)
            pub.publish_one(releases[stage], output, title='Watch SDR test ' + STAGES[stage][0],
                            notes=NOTICE, prerelease=True)
            pub.publish_index(indexes[stage], expected_parent=parent, expected_current=current)
    print(('Published' if mutate else 'Read-only preflight passed for') + ' SDR stage ' + stage)


def freeze(args):
    require(not args.output.exists(), 'Refusing to replace an existing acceptance record')
    raw = pub.gh('api', f'repos/{REPOSITORY}/actions/artifacts/{args.artifact_id}/zip')
    content = pub.api(f'repos/{REPOSITORY}/contents/release-index.json?ref={BASELINE["index_source"]}')
    a = dict(schema=1, repository=REPOSITORY, source_sha=args.source_sha,
             run_id=args.run_id, run_attempt=args.run_attempt, artifact_id=args.artifact_id,
             name='twatch-sdr-upgrade-' + args.source_sha, sha256=pub.sha(raw),
             base_index_commit=BASELINE['index_source'], base_index=decode(base64.b64decode(content['content'])))
    verify_ci(validate_acceptance(a)); verify_bundle(a, raw)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pub.write_input(args.output, pub.encoded(a))
    print('Frozen acceptance candidate; review and commit before manual publication:', args.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    f = commands.add_parser('freeze')
    for name in ('run-id', 'run-attempt', 'artifact-id'):
        f.add_argument('--' + name, type=int, required=True)
    f.add_argument('--source-sha', required=True); f.add_argument('--output', type=Path, default=ACCEPTANCE)
    for action in ('verify', 'preflight', 'publish', 'confirmation'):
        sub = commands.add_parser(action)
        sub.add_argument('--acceptance', type=Path, default=ACCEPTANCE)
        if action != 'confirmation': sub.add_argument('--artifact', type=Path)
        if action in ('preflight', 'publish'):
            sub.add_argument('--stage', choices=STAGES, required=True)
            sub.add_argument('--operator-confirmation', default='')
        if action != 'verify': sub.add_argument('--expected-index-commit', required=True)
    args = parser.parse_args()
    if args.action == 'freeze': return freeze(args)
    a = validate_acceptance(decode(args.acceptance.read_bytes()))
    if args.action == 'confirmation':
        print(confirmation(a, args.expected_index_commit)); return
    raw = args.artifact.read_bytes() if args.artifact else download(a)
    if args.action == 'verify':
        verify_bundle(a, raw); print('Verified exact accepted SDR artifact; no publication'); return
    require(args.acceptance.resolve() == ACCEPTANCE, 'Publication uses only canonical committed SDR acceptance')
    publish(a, raw, args.stage, args.expected_index_commit, args.operator_confirmation, mutate=args.action == 'publish')


if __name__ == '__main__':
    main()
