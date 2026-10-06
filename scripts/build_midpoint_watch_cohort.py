#!/usr/bin/env python3
"""Build the exact midpoint-origin 1.0.6 OTA variant from a final 1.0.5 bundle.

Requires the unchanged 1.0.3 native bridge first. Emits native+bootfs only, never a
full initial image, and never edits accepted inputs, releases, catalogs or devices.
"""
import argparse
from pathlib import Path
import json

import build_next_watch_cohort as base
from check_runtime_store_admission import admit_cohort
from current_bootfs import build as build_store
from current_cohort import package, parse
from midpoint_upgrade import (ROOT, PROFILE, VERSION, MIDPOINT_SOURCE, INSTALLED_RUNTIME,
    read_midpoint, read_standard_candidate, standard_proof_digest, adapt_candidate, check_policy,
    require, sha, encoded, metadata)


def prepare(installed_bin, previous_bundle, candidate_bundle, runtime, native_dir, output,
            source_root=ROOT, *, previous_runtime, previous_native_dir):
    output, source_root = Path(output), Path(source_root).resolve()
    require(not output.exists(), 'Output must be new')
    head = base.checked_source(source_root)
    _, prior, prior_identity, bridge, bridge_elf, old_native = base.read_previous(
        previous_bundle, previous_native_dir, previous_runtime)
    firmware, elf, native = base.read_native(native_dir, runtime)
    standard, standard_proof, requirements_bytes, evidence = read_standard_candidate(
        candidate_bundle, prior, prior_identity, old_native, native, firmware, elf,
        previous_runtime, runtime, expected_source=head)
    full, midpoint, identity, custody = read_midpoint(installed_bin)
    following = adapt_candidate(standard, firmware, VERSION)
    policy = check_policy(midpoint, following, prior, standard, firmware, VERSION)
    # The native bridge clones the midpoint byte-for-byte, retaining its 1.0.2
    # source identity. It must not be relabelled as accepted 1.0.4.
    bridge_self = admit_cohort(previous_runtime, bridge_elf, midpoint, midpoint)
    admitted = admit_cohort(previous_runtime, bridge_elf, midpoint, following)
    self_admitted = admit_cohort(runtime, elf, following, following)
    store, packing = build_store(following)
    payload, ota = package(parse(following['cohort.json']), firmware, store)
    standard_path = Path(candidate_bundle)
    license_bytes = (standard_path / 'LICENSES.zip').read_bytes()
    proof = {'schema': 1, 'profile': PROFILE, 'watch_source': head,
             'version': VERSION, 'source_cohort': identity,
             'target_cohort': parse(following['cohort.json']),
             'source_initial_image_sha256': sha(full),
             'source_store_sha256': custody['store_sha256'],
             'source_baseline_sha256': sha((ROOT / 'apps/midpoint-origin-baseline.json').read_bytes()),
             'original_installed_runtime': INSTALLED_RUNTIME,
             'standard_candidate_version': base.VERSION,
             'standard_candidate_sha256': standard_proof['ota']['sha256'],
             'standard_candidate_proof_sha256': standard_proof_digest(standard_path),
             'standard_configuration': standard_proof['configuration'],
             'bridge': {'release_version': '1.0.3', 'runtime_version': base.RUNTIME_VERSION,
                        'runtime_source': base.RUNTIME, 'native_sha256': sha(bridge),
                        'native_elf_sha256': sha(bridge_elf), 'native_bytes': len(bridge),
                        'retained_source_revision': MIDPOINT_SOURCE, 'retained_cohort_version': '1.0.2',
                        'retained_store_sha256': custody['store_sha256'],
                        'asset': 'riscrte-runtime-0.1.34.bin',
                        'url': 'https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/releases/download/firmware-v1.0.3/riscrte-runtime-0.1.34.bin'},
             'native_candidate_sha256': sha((Path(native_dir) / 'candidate.json').read_bytes()),
             'native_elf_sha256': sha(elf), 'runtime_evidence': evidence,
             'runtime_requirements': standard_proof['runtime_requirements'],
             'runtime_requirements_sha256': sha(requirements_bytes),
             'ota': ota, 'policy': policy, 'packing': packing,
             'bridge_retained_store_self_admission': bridge_self,
             'installed_runtime_admission': admitted, 'target_self_admission': self_admitted,
             'files': {name: metadata(data) for name, data in sorted(following.items())},
             'licenses_sha256': sha(license_bytes),
             'payload_members': ['native', 'bootfs'], 'initial_image_emitted': False,
             'publication_performed': False, 'hardware_qualified': False}
    output.mkdir(parents=True)
    for name, data in following.items():
        path = output / 'store' / name
        path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(data)
    for name, data in ((ota['asset'], payload), ('bootfs.bin', store),
                       ('LICENSES.zip', license_bytes), ('runtime-requirements.json', requirements_bytes),
                       ('midpoint-watch-build-proof.json', encoded(proof))):
        (output / name).write_bytes(data)
    (output / 'INSTALL.txt').write_text(
        'Watch 1.0.6 exact midpoint-origin offline OTA candidate.\n'
        'For source 27fba6f26a64501eadd308d4b1e7225c712ea50b only.\n'
        'Step 1: existing native-only 1.0.3 bridge installs Runtime 0.1.34, retaining the midpoint store.\n'
        'Restart and verify healthy Clock before step 2. The retained cohort remains midpoint 1.0.2.\n'
        'Step 2: this canonical 1.0.6 paired-cohort payload installs native + bootfs together.\n'
        'Run the exact midpoint upgrade proof before publication or installation.\n'
        'Both stages exclude NVS and app-data and preserve the preceding rollback pair.\n'
        'Frozen 1.0.4 and ordinary 1.0.5 payloads do not admit this midpoint source.\n'
        'Do not relabel the installed source, reflash a full initial image, write empty app-data,\n'
        'or serial-flash either OTA payload at offset zero.\n'
        'The installed updater requires canonical per-version names: do not suffix this asset.\n'
        'Assets and reviewed stage catalogs require separate authorized publication.\n'
        'This command performs no publication, device operation or hardware qualification.\n')
    (output / 'SHA256SUMS').write_text(''.join(f'{sha(p.read_bytes())}  {p.name}\n'
                                            for p in sorted(output.iterdir()) if p.is_file()))
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('installed-bin', 'previous-bundle', 'candidate-bundle', 'runtime', 'native-dir',
                 'previous-runtime', 'previous-native-dir', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    a = parser.parse_args()
    proof = prepare(a.installed_bin, a.previous_bundle, a.candidate_bundle, a.runtime, a.native_dir,
                    a.output, a.source_root, previous_runtime=a.previous_runtime,
                    previous_native_dir=a.previous_native_dir)
    print(json.dumps(proof['ota'], sort_keys=True))


if __name__ == '__main__':
    main()
