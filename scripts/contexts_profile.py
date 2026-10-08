"""Isolated 1.0.13 source/build contract; historical Watch lanes stay frozen."""
import copy
import hashlib
import json
from pathlib import Path
import re

from current_apps_overlay import APPS as PRIOR_APPS, ROOT, encoded, metadata, require
from build_wifi_common import read_zip
from current_cohort import parse as parse_cohort

PROFILE = 'watch-contexts-cohort-v1'
VERSION = '1.0.13'
RUNTIME_VERSION = '0.1.55'
APPS = (*PRIOR_APPS, 'contexts')
CAPABILITY = {'capability': 'contexts.service', 'api': 1}
GRANT = {**CAPABILITY, 'instance_id': 0}
SERVICE_MANIFEST = 'contexts/manifest.json'
SERVICE_FILES = {'contexts/manifest.json', 'contexts/driver.elf'}
CONTEXT_ENTRY = {'display_name': 'Contexts', 'file_name': 'contexts.elf', 'icon': 'solid:f015'}

def version(value):
    require(isinstance(value, str) and re.fullmatch(r'\d+\.\d+\.\d+', value), 'Invalid component version')
    return tuple(map(int, value.split('.')))

def baseline_contract(root=ROOT):
    value = json.loads((Path(root) / 'apps/contexts-baseline.json').read_text())
    require(value['schema'] == 1 and value['accepted_cohort']['version'] == '1.0.12', 'Wrong Contexts baseline')
    require(value['accepted_cohort']['runtime_version'] == RUNTIME_VERSION, 'Baseline Runtime differs')
    require(value['artifacts']['accepted-store.zip']['sha256'] == 'b8e6612d11b72ef8f8cac2fbd569d86e82b1f2f9ae0c1b3093911720b4bd1a11', 'Accepted release archive pin changed')
    require(value['accepted_cohort']['firmware_sha256'] == 'd6474c004a8da30945930de5d0757d1c80e25db7ecda7e13d07d32f805ca30fd', 'Accepted native firmware pin changed')
    return value

def configuration(root=ROOT, *, allow_pending=False):
    c = json.loads((Path(root) / 'apps/contexts-sources.json').read_text())
    require(c['schema'] == 1 and c['profile'] == PROFILE and c['product_version'] == VERSION and
            c['runtime_version'] == RUNTIME_VERSION, 'Wrong Contexts profile')
    require(set(c['app_versions']) == set(APPS) == set(c['source_app_versions']), 'Incomplete Contexts app versions')
    old = json.loads((Path(root) / 'apps/runtime-features-sources.json').read_text())
    for name in PRIOR_APPS:
        require(version(c['app_versions'][name]) > version(old['app_versions'][name]), 'Rebuilt app version did not advance: ' + name)
    for value in c['source_app_versions'].values():
        version(value)
    require(c['app_versions']['contexts'] == '0.1.0' and c['contexts_service'] == {'id': 'contexts-service', 'version': '0.1.0'}, 'Wrong new component identity')
    require(set(c['sources']) == set(old['sources']), 'Changed source repository scope')
    for name, source in c['sources'].items():
        require(source['repository'] == old['sources'][name]['repository'], 'Changed source repository: ' + name)
        if allow_pending and name in ('system-apps', 'utilities') and source['commit'] is None:
            continue
        require(re.fullmatch('[0-9a-f]{40}', source['commit'] or '') is not None, 'Pending or invalid source pin: ' + name)
    require(c['sources']['runtime'] == old['sources']['runtime'] and c['sources']['productivity'] == old['sources']['productivity'], 'Unrequested Runtime/Productivity source change')
    require(c['drivers'] == old['sdr'], 'Context driver header pin changed')
    require(c['features'] == {**old['features'], 'contexts': True}, 'An accepted feature was lost')
    require((c['app_count'], c['catalog_count'], c['prior_provider_artifacts'], c['provider_selections'], c['max_app_grants']) == (23, 21, 22, 24, 15), 'Context capacity contract changed')
    b = baseline_contract(root)
    require(c['baseline'] == {'accepted_store': b['artifacts']['accepted-store.zip'], 'accepted_source': b['accepted_source']}, 'Baseline authority changed')
    return c

def baseline_inputs(archive, root=ROOT, unpacked=None):
    archive = Path(archive)
    b = baseline_contract(root)
    require(metadata(archive.read_bytes()) == b['artifacts']['accepted-store.zip'], 'Accepted store ZIP differs from published custody')
    files = read_zip(archive)
    require({n: metadata(data) for n, data in files.items()} == b['store_inventory'], 'Accepted store inventory differs')
    require(parse_cohort(files['cohort.json']) == b['accepted_cohort'], 'Accepted cohort identity differs')
    if unpacked is not None:
        unpacked = Path(unpacked)
        actual = {p.relative_to(unpacked).as_posix(): p.read_bytes() for p in unpacked.rglob('*') if p.is_file()}
        require(actual == files, 'Unpacked store differs from published accepted bytes')
    boot = json.loads(files['boot.json'])
    require(len(boot['app_capabilities']) == 22 and len(boot['drivers']) == 23, 'Accepted policy inventory differs')
    require(len({d['manifest'] for d in boot['drivers']}) == 22, 'Accepted provider artifact inventory differs')
    require({r['manifest'] for r in boot['app_capabilities']} == {n + '.json' for n in PRIOR_APPS}, 'Accepted app inventory differs')
    return files

def catalog(root=ROOT):
    result = copy.deepcopy(baseline_contract(root)['catalog']) + [dict(CONTEXT_ENTRY)]
    require(len(result) == 21 and len({r['icon'] for r in result}) == 21, 'Context catalog collision')
    require({r['file_name'] for r in result} == {n + '.elf' for n in APPS if n not in ('default', 'springboard')}, 'Context catalog lost an app')
    return result

def upgrade_boot(previous, identity):
    b = copy.deepcopy(previous)
    require(b.get('provider_activation') == 'demand' and 'cohort_migration' not in b, 'Unexpected accepted lifecycle/migration')
    require(len(b['drivers']) == 23 and not any(d['manifest'] == SERVICE_MANIFEST for d in b['drivers']), 'Unexpected Contexts provider')
    b['drivers'].append({'manifest': SERVICE_MANIFEST})
    for row in b['app_capabilities']:
        require(row['manifest'] in {n + '.json' for n in PRIOR_APPS}, 'Unexpected prior app policy')
        require(not any(g['capability'] == CAPABILITY['capability'] for g in row['grants']), 'Duplicate Contexts authority')
        row['grants'].append(dict(GRANT))
        require(len(row['grants']) <= 15, 'Context grant bound exceeded')
    # Namespace 1 was already granted to every accepted app. This is the narrow
    # existing Runtime migration for one genuinely new app, not an old-app
    # expansion or any sharing of the source-owned model namespaces.
    shared = {'capability': 'storage.key-value', 'api': 1, 'instance_id': 1}
    require(all(shared in row['grants'] for row in previous['app_capabilities']), 'Namespace 1 is not universally shared')
    exemplar = next(r for r in b['app_capabilities'] if r['manifest'] == 'springboard.json')
    b['app_capabilities'].append({'manifest': 'contexts.json', 'grants': copy.deepcopy(exemplar['grants'])})
    b['cohort_migration'] = {'schema': 1,
        'from': {k: identity[k] for k in ('product', 'version', 'source_revision')},
        'to': {'product': identity['product'], 'version': VERSION},
        'shared_key_value': [{'application_id': 'contexts', 'api': 1, 'namespace': 1}]}
    require(len(b['app_capabilities']) == 23 and len(b['drivers']) == 24, 'Context policy capacity differs')
    return b

def app_manifest(name, previous, configuration, boot):
    if name in PRIOR_APPS:
        result = copy.deepcopy(previous)
        require(not any(q['capability'] == CAPABILITY['capability'] for q in result['requires']), 'Duplicate Contexts requirement')
        result['requires'].append(dict(CAPABILITY))
    else:
        row = next(r for r in boot['app_capabilities'] if r['manifest'] == 'contexts.json')
        result = {'type': 'application', 'id': 'contexts', 'architecture': 'xtensa-esp32s3',
                  'file_name': 'contexts.elf', 'entry': 'app_main',
                  'requires': [{k: g[k] for k in ('capability', 'api')} for g in row['grants']]}
    result['version'] = configuration['app_versions'][name]
    return result

def check_policy(previous, following, c, root=ROOT):
    identity = parse_cohort(previous['cohort.json'])
    boot = upgrade_boot(json.loads(previous['boot.json']), identity)
    require(set(following) == set(previous) | SERVICE_FILES | {'contexts.elf', 'contexts.json'}, 'Context store inventory changed')
    require(following['board.json'] == previous['board.json'], 'Context board changed')
    require(json.loads(following['boot.json']) == boot, 'Context boot authority changed')
    after = parse_cohort(following['cohort.json'])
    expected = {**identity, 'version': VERSION, 'source_revision': after['source_revision']}
    require(after == expected, 'Context cohort changed native image/layout/identity')
    providers = {d['manifest'] for d in json.loads(previous['boot.json'])['drivers']}
    for manifest in providers:
        folder = str(Path(manifest).parent)
        for name in (manifest, folder + '/driver.elf'):
            require(following[name] == previous[name], 'Prior provider changed: ' + name)
    for name in APPS:
        old = json.loads(previous[name + '.json']) if name in PRIOR_APPS else None
        require(json.loads(following[name + '.json']) == app_manifest(name, old, c, boot), 'Context app manifest authority/version differs: ' + name)
        require(following[name + '.elf'] and (name not in PRIOR_APPS or following[name + '.elf'] != previous[name + '.elf']), 'Context app was not rebuilt: ' + name)
    for row in boot['app_capabilities']:
        m = json.loads(following[row['manifest']])
        requests = {(r['capability'], r['api']) for r in m['requires']}
        require(len(requests) == len(m['requires']) and requests == {(g['capability'], g['api']) for g in row['grants']}, 'Context grant/requirement mismatch')
        require(len(m['requires']) <= 16 and len(row['grants']) <= 15, 'Context app bound exceeded')
    service = json.loads(following[SERVICE_MANIFEST])
    require(bool(following['contexts/driver.elf']), 'Context service ELF is empty')
    require(service['id'] == c['contexts_service']['id'] and service['version'] == c['contexts_service']['version'] and
            service['driver_abi'] == 2 and service['architecture'] == 'xtensa-esp32s3' and service['file_name'] == 'driver.elf', 'Context service identity differs')
    require(service['provides'] == [CAPABILITY] and service['requires'] == [
        {'capability': 'platform.clock', 'api': 1}, {'capability': 'audio.input', 'api': 1}, {'capability': 'radio.iq', 'api': 1}], 'Context service expanded authority')
    return {'prior_app_count': 22, 'candidate_app_count': 23, 'prior_provider_artifacts': 22,
            'provider_selections': 24, 'all_prior_provider_bytes_preserved': True,
            'max_app_grants': max(len(r['grants']) for r in boot['app_capabilities']),
            'only_new_persistent_authority': 'contexts storage.key-value@1 namespace1',
            'runtime_changed': False, 'catalog_count': len(catalog(root))}
