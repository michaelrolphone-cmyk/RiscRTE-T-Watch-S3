"""Exact installed-midpoint custody and bounded alternative cohort metadata.

The accepted 1.0.4 and ordinary 1.0.5 products are read-only inputs. Runtime's
source-bound migration policy is reused without broadening its grammar.
"""
import copy
from pathlib import Path

import build_next_watch_cohort as base
from current_cohort import create, encode, parse, verify, package
from read_only_spiffs import read_image
from watch_release_index import version_tuple

ROOT = Path(__file__).resolve().parents[1]
PROFILE = 'midpoint-27fba6f2'
VERSION = '1.0.6'
MIDPOINT_SOURCE = '27fba6f26a64501eadd308d4b1e7225c712ea50b'
INSTALLED_RUNTIME = 'e08609b465d9368d4e6efc45e377adbdbbb706a1'
INSTALLED_VERSION = '0.1.33'
MIDPOINT_SHA = '2225261601729774c7d0d42a88ab1a705c55aa856097af292dce9fa06dd659bf'
NEW_APPS = ('waterfall', *base.NEW_APPS)
NEW_FILES = base.NEW_FILES | {'waterfall.elf', 'waterfall.json',
                            's3-radio-iq/driver.elf', 's3-radio-iq/manifest.json'}
require, sha, encoded, document, metadata = base.require, base.sha, base.encoded, base.document, base.metadata


def baseline():
    result = document((ROOT / 'apps/midpoint-origin-baseline.json').read_bytes())
    require(result['schema'] == 1 and result['profile'] == PROFILE
            and result['source_revision'] == MIDPOINT_SOURCE
            and result['initial_image_sha256'] == MIDPOINT_SHA
            and result['runtime_source'] == INSTALLED_RUNTIME
            and result['runtime_version'] == INSTALLED_VERSION
            and result['initial_image_bytes'] == 0x1000000
            and result['store_offset'] == 0x2f0000 and result['store_bytes'] == base.STORE_BYTES,
            'Wrong reviewed midpoint baseline')
    return result


def read_midpoint(filename, installed_runtime=None):
    custody = baseline()
    full = Path(filename).read_bytes()
    require(len(full) == custody['initial_image_bytes'] and sha(full) == MIDPOINT_SHA,
            'Exact installed midpoint BIN custody differs')
    store = full[custody['store_offset']:custody['store_offset'] + base.STORE_BYTES]
    require(sha(store) == custody['store_sha256'], 'Midpoint store image differs')
    files = read_image(store, base.STORE_BYTES)
    require({name: metadata(data) for name, data in files.items()} == custody['files'],
            'Midpoint extracted files differ')
    identity = parse(files['cohort.json'])
    require(identity == custody['cohort'], 'Midpoint cohort identity differs')
    firmware = full[0x10000:0x10000 + identity['firmware_size']]
    verify(identity, firmware, version='1.0.2', runtime_version=INSTALLED_VERSION,
           source_revision=MIDPOINT_SOURCE)
    if installed_runtime is not None:
        base.checked_source(installed_runtime, INSTALLED_RUNTIME)
        bank = base.module('midpoint_original_bank_images', Path(installed_runtime) / 'scripts/paired_bank_images.py')
        require(full[0xff2000:0xff4000] == bank.initial_bank_state(firmware, store, app_data=True),
                'Midpoint paired journal differs')
    return full, files, identity, custody


def migration(version=VERSION):
    # The installed provider requires a canonical per-version asset name. A new
    # product version prevents collisions with the ordinary 1.0.5 payload.
    require(version == VERSION and version_tuple(version) > version_tuple(base.VERSION),
            'Midpoint profile needs a distinct newer product version')
    return {'schema': 1, 'from': {'product': 'twatch-s3', 'version': '1.0.2',
                                'source_revision': MIDPOINT_SOURCE},
            'to': {'product': 'twatch-s3', 'version': version},
            'shared_key_value': [{'application_id': name, 'api': 1, 'namespace': 1}
                                 for name in NEW_APPS]}


def adapt_candidate(standard, firmware, version):
    """Only origin/target metadata changes; no app, provider or authority edits."""
    identity = parse(standard['cohort.json'])
    verify(identity, firmware, version=base.VERSION, runtime_version=base.CANDIDATE_VERSION)
    following = dict(standard)
    boot = document(standard['boot.json'])
    require(boot.get('cohort_migration') == base.migration(), 'Ordinary candidate migration differs')
    boot['cohort_migration'] = migration(version)
    following['boot.json'] = encoded(boot)
    following['cohort.json'] = encode(create(version, identity['runtime_version'],
                                           identity['source_revision'], firmware))
    return following


def check_policy(midpoint, following, standard_previous, standard, firmware, version):
    ordinary = base.check_policy(standard_previous, standard)
    require(following == adapt_candidate(standard, firmware, version),
            'Midpoint variant may change only exact origin/target metadata')
    require(following['board.json'] == midpoint['board.json'], 'Midpoint hardware board changed')
    require(set(following) == set(midpoint) | NEW_FILES, 'Unexpected midpoint inventory change')
    before, after = document(midpoint['boot.json']), document(following['boot.json'])
    require('cohort_migration' not in before, 'Installed midpoint already has migration authority')
    old_apps = {row['manifest']: row for row in before['app_capabilities']}
    next_apps = {row['manifest']: row for row in after['app_capabilities']}
    require(len(old_apps) == len(before['app_capabilities'])
            and len(next_apps) == len(after['app_capabilities'])
            and set(next_apps) == set(old_apps) | {n + '.json' for n in NEW_APPS},
            'Midpoint application policy inventory differs')
    owners = {}
    for name, row in old_apps.items():
        require(next_apps[name] == row, 'Midpoint existing app grants changed: ' + name)
        original, current = document(midpoint[name]), document(following[name])
        require(base.manifest_authority(original) == base.manifest_authority(current),
                'Midpoint existing app authority changed: ' + name)
        owners[original['id']] = sorted(base.grants(row['grants']))
    old_drivers = before['drivers']
    additions = {'s3-radio-iq/manifest.json', 'ble-hid/manifest.json'}
    require([row for row in after['drivers'] if row['manifest'] not in additions] == old_drivers
            and len(after['drivers']) == len(old_drivers) + 2,
            'Midpoint existing provider bindings changed')
    for row in old_drivers:
        name = row['manifest']
        require(base.manifest_authority(document(midpoint[name])) ==
                base.manifest_authority(document(following[name])),
                'Midpoint existing provider authority changed: ' + name)
    stripped = copy.deepcopy(after)
    stripped.pop('cohort_migration')
    stripped['app_capabilities'] = [row for row in after['app_capabilities'] if row['manifest'] in old_apps]
    stripped['drivers'] = old_drivers
    require(stripped == before, 'Unexpected midpoint boot authority change')
    return {'profile': PROFILE, 'migration': migration(version), 'prior_app_owners': owners,
            'prior_provider_bindings': old_drivers, 'ordinary_candidate_policy': ordinary,
            'hardware_board_sha256': sha(midpoint['board.json']),
            'only_standard_store_changes': ['boot.json', 'cohort.json']}


def standard_proof_digest(bundle):
    # Preserve the exact file bytes, including accepted noncanonical JSON.
    return sha((Path(bundle) / 'next-watch-build-proof.json').read_bytes())


def read_standard_candidate(bundle, previous, old_identity, old_native, native, firmware, elf,
                            previous_runtime, runtime, expected_source=None):
    """Recheck all three candidate representations and existing packaging proof."""
    root = Path(bundle)
    proof = document((root / 'next-watch-build-proof.json').read_bytes())
    requirements_bytes = (root / 'runtime-requirements.json').read_bytes()
    requirements = base.check_requirements(document(requirements_bytes), native)
    evidence = base.runtime_evidence(previous_runtime, runtime, old_native, native)
    require(native['firmware_version'] == base.CANDIDATE_VERSION,
            'Midpoint final candidate requires Runtime 0.1.35')
    require(expected_source is None or proof['watch_source'] == expected_source,
            'Ordinary candidate must come from this exact Watch source')
    payload = (root / ('twatch-s3-cohort-' + base.VERSION + '.bin')).read_bytes()
    require(len(payload) == len(firmware) + base.STORE_BYTES and payload[:len(firmware)] == firmware,
            'Ordinary payload must contain exact native followed by bootfs')
    store = payload[len(firmware):]
    require((root / 'bootfs.bin').read_bytes() == store, 'Ordinary bootfs differs')
    following = read_image(store, base.STORE_BYTES)
    extracted = {p.relative_to(root / 'store').as_posix(): p.read_bytes()
                 for p in (root / 'store').rglob('*') if p.is_file()}
    require(extracted == following, 'Ordinary extracted store differs')
    identity = parse(following['cohort.json'])
    verify(identity, firmware, version=base.VERSION, runtime_version=base.CANDIDATE_VERSION,
           source_revision=proof['watch_source'])
    _, ota = package(identity, firmware, store)
    require(proof['configuration']['sources']['runtime']['commit'] == native['source_sha']
            and proof['source_cohort'] == old_identity and proof['target_cohort'] == identity
            and proof['source_initial_image_sha256'] == base.FULL_SHA
            and proof['source_cohort_sha256'] == base.COHORT_SHA
            and proof['previous_native_sha256'] == base.NATIVE_SHA
            and proof['previous_native_elf_sha256'] == base.ELF_SHA
            and proof['native_elf_sha256'] == sha(elf) and proof['ota'] == ota
            and proof['runtime_evidence'] == evidence
            and proof['runtime_requirements'] == requirements
            and proof['runtime_requirements_sha256'] == sha(requirements_bytes)
            and proof['files'] == {n: metadata(b) for n, b in following.items()},
            'Ordinary candidate proof/bytes differ')
    policy = base.check_policy(previous, following)
    require(proof['policy'] == document(encoded(policy)), 'Ordinary candidate policy proof differs')
    return following, proof, requirements_bytes, evidence
