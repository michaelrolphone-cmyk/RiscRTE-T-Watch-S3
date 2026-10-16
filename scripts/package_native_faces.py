#!/usr/bin/env python3
"""Package native Home with exact official native/store custody and fault proof."""
import argparse, json, subprocess, sys, tempfile
from pathlib import Path
from watch_native_faces import ROOT, DOCS, PINS, clean, encoded, files, git, need, require_final, sha, verify_baseline, verify_metadata
from package_shared_native_ui import archive, checksums, verify_native_bin
from stage_native_faces import NATIVE
from qualify_native_faces import EXPECTED_REPORTS
PREFIX = 'TWatch-1.1.38-Native-Faces'


def make_factory(baseline, firmware, store, runtime):
    need(len(baseline) == 0x1000000 and sha(baseline) == PINS['baseline_sha256'], 'Exact 1.1.37 factory required')
    sys.path.insert(0, str(runtime/'scripts'))
    from paired_bank_images import initial_bank_state
    from prepare_preserving_update import layout, pair
    geometry = layout(baseline); need(geometry[0] and geometry[3] == 0x550000, 'Existing ABI3 geometry required')
    _, old_native, _ = pair(baseline, 0, geometry)
    need(old_native == firmware, 'Native firmware must remain byte-identical')
    result = bytearray(baseline); result[0x2f0000:0x840000] = store
    state = initial_bank_state(firmware, store, True, True)
    result[0xff2000:0xff2000+len(state)] = state
    _, actual_firmware, actual_store = pair(result, 0, geometry)
    need(actual_firmware == firmware and actual_store == store, 'Factory pair mismatch')
    for start, end in ((0, 0x2f0000), (0x840000, 0xff2000), (0xff2000+len(state), 0x1000000)):
        need(result[start:end] == baseline[start:end], 'Protected factory range changed')
    return bytes(result)


def instructions():
    return ('T-Watch 1.1.38 native Home preserving update from exact 1.1.37\n\n'
            'This kit never connects to hardware. The full factory image erases saved data.\n'
            'Obtain a fresh full 16 MiB readback through an explicitly authorized device flow.\n'
            'Run Python 3: python prepare_preserving_update.py --snapshot DEVICE-READBACK.bin\n'
            ' --baseline baseline-1.1.37.bin --candidate candidate-1.1.38.bin\n'
            ' --baseline-sha256 '+PINS['baseline_sha256']+' --output NEW-PLAN-DIRECTORY\n\n'
            'The plan rejects a different active firmware/store, changed layout, corrupt readback,\n'
            'unconfirmed source or ambiguous OTA selection. Read the generated plan.json.\n'
            'Stage only the inactive firmware, store and bank-state writes without resetting.\n'
            'Read back and verify all three hashes, then write the separate OTA selection\n'
            'sector LAST. Verify that sector before resetting. Preserve NVS, AppData, the\n'
            'active pair and SD data if present. Never erase_flash or overwrite the full\n'
            'factory image for a preserving update. Failed health confirmation uses the\n'
            'existing rollback. Non-Plus T-Watch-S3 with BMA423; confirm radio/antenna variant.\n'
            'Host software tests and source builds do not qualify physical hardware.\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'runtime', 'composition', 'admission', 'admission-sanitized', 'preservation', 'qualification', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--source-revision', required=True); a = p.parse_args()
    for name, value in vars(a).items():
        if isinstance(value, Path): setattr(a, name, value.resolve())
    require_final(); clean(ROOT, a.source_revision); clean(a.runtime, PINS['runtime_revision'])
    need(not a.output.exists(), 'Output must be new')
    baseline = a.baseline.read_bytes(); need(sha(baseline) == PINS['baseline_sha256'], 'Wrong published baseline')
    from read_only_spiffs import read_image
    before = read_image(baseline[0x2f0000:0x840000], 0x550000); verify_baseline(before)
    native = a.runtime/'.pio/build/watch-native-ui'; verify_native_bin(native)
    firmware = (native/'firmware.bin').read_bytes(); elf = (native/'firmware.elf').read_bytes()
    need(sha(firmware) == NATIVE['files']['firmware.bin']['sha256'] and sha(elf) == NATIVE['files']['firmware.elf']['sha256'], 'Published native bytes changed')
    custody = json.loads((native/'native-faces-custody.json').read_text())
    need(custody['native_origin_product_revision'] == PINS['baseline_source'] and custody['baseline_native_bytes_preserved'], 'Native custody differs')
    store = (a.composition/'store.bin').read_bytes(); current = files(a.composition/'store')
    need(len(store) == 0x550000 and read_image(store, 0x550000) == current, 'Complete packed store differs')
    changed = verify_metadata(before, current, firmware, a.source_revision)
    composition = json.loads((a.composition/'composition.json').read_text())
    need(composition['store_sha256'] == sha(store) and composition['native_sha256'] == sha(firmware), 'Composition differs')
    need(composition['packing']['empty_blocks'] >= 2, 'Insufficient SPIFFS reserve')
    from check_runtime_store_admission import store_digest
    admissions = {}
    for label, path in (('normal', a.admission), ('sanitized', a.admission_sanitized)):
        report = json.loads((path/'admission.json').read_text())
        need(report['prepared'] and report['cohort_validated'] and report['elf_count'] == 59, 'Incomplete admission')
        need(report['hardware_calls'] == report['storage_calls'] == 0 and report['sanitized'] == (label == 'sanitized'), 'Wrong admission mode/I/O')
        need(report['producer_sha256'] == sha((ROOT/'scripts/verify_native_faces.py').read_bytes()), 'Admission producer differs')
        need(report['active_store_sha256'] == store_digest(before) and report['candidate_store_sha256'] == store_digest(current), 'Admission store differs')
        need(report['native_elf_sha256'] == sha(elf), 'Admission native ELF differs')
        admissions[label] = report
    proof = json.loads((a.preservation/'preservation.json').read_text())
    need(proof['baseline_version'] == PINS['baseline_version'] and proof['baseline_sha256'] == sha(baseline), 'Preservation baseline differs')
    need(len(proof['cases']) == 272 and proof['candidate_native_sha256'] == sha(firmware) and proof['candidate_store_sha256'] == sha(store), 'Preservation candidate differs')
    with tempfile.TemporaryDirectory(prefix='native-faces-preservation-') as td:
        output = Path(td)/'proof'
        subprocess.run([sys.executable, str(ROOT/'scripts/test_native_faces_preservation.py'), '--runtime', str(a.runtime), '--baseline', str(a.baseline), '--firmware', str(native/'firmware.bin'), '--store', str(a.composition/'store.bin'), '--output', str(output)], check=True)
        need(json.loads((output/'preservation.json').read_text()) == proof, 'Preservation proof does not reproduce')
    qualification = json.loads((a.qualification/'qualification.json').read_text())
    need(qualification['twice_reproduced'] and qualification['home_sha256'] == PINS['home_sha256'], 'Home reproducibility missing')
    need(qualification['producer_sha256'] == sha((ROOT/'scripts/qualify_native_faces.py').read_bytes()), 'Qualification producer differs')
    need(qualification['compiler_sha256'] == PINS['compiler_sha256'], 'Qualification compiler differs')
    need(set(qualification['reports']) == EXPECTED_REPORTS, 'Incomplete qualification reports')
    for name in ('shared', 'system', 'utilities'): need(qualification[name+'_revision'] == PINS[name+'_revision'], 'Qualification source differs')
    for name, digest in qualification['reports'].items(): need(sha((a.qualification/(name+'.log')).read_bytes()) == digest, 'Qualification log differs')
    for index in (1, 2): need((a.qualification/('build-'+str(index))/'default.elf').read_bytes() == current['default.elf'], 'Packaged Home differs from source rebuild')
    factory = make_factory(baseline, firmware, store, a.runtime); a.output.mkdir(parents=True)
    factory_name = PREFIX+'-factory-erases-data-0x0.bin'; (a.output/factory_name).write_bytes(factory)
    metadata = dict(version=PINS['version'], home_version=PINS['home_version'], source_revision=a.source_revision,
                    baseline_version=PINS['baseline_version'], baseline_source=PINS['baseline_source'], baseline_sha256=sha(baseline),
                    runtime_revision=PINS['runtime_revision'], runtime_version=PINS['runtime_version'],
                    shared_revision=PINS['shared_revision'], system_revision=PINS['system_revision'], utilities_revision=PINS['utilities_revision'],
                    firmware_sha256=sha(firmware), native_elf_sha256=sha(elf), store_sha256=sha(store), factory_sha256=sha(factory),
                    home_sha256=PINS['home_sha256'], home_bytes=PINS['home_bytes'], home_preferences='nvs',
                    baseline_native_evidence_sha256=NATIVE['evidence_sha256'], baseline_native_bytes_preserved=True,
                    native_bin_reproduced_from_admitted_elf=True, home_twice_reproduced_from_pinned_sources=True,
                    changed_store_files=changed, unchanged_store_files=118, file_count=121, elf_count=59,
                    empty_store_blocks=composition['packing']['empty_blocks'], home_manifest_authority_preserved=True,
                    native_faces_qualification=qualification['reports'], preservation_cases=len(proof['cases']),
                    preserved_springboard_sha256=sha(current['springboard.elf']), preserved_sdr_sha256=sha(current['waterfall.elf']),
                    installation_method='preserving-update-from-exact-1.1.37-or-factory-flash', factory_erases_saved_data=True,
                    preserving_update_requires_fresh_full_readback=True, hardware_model='non-Plus T-Watch-S3 with BMA423',
                    radio_antenna_variant_requires_confirmation=True, hardware_tested=False, device_accessed=False)
    (a.output/'release.json').write_bytes(encoded(metadata))
    kit = {}
    for name in ('prepare_preserving_update.py', 'paired_bank_images.py', 'spiffs_image.py'):
        data = (a.runtime/'scripts'/name).read_bytes()
        need(data == git(a.runtime, 'show', PINS['runtime_revision']+':scripts/'+name), 'Update helper changed')
        kit[name] = data
    kit.update({'baseline-1.1.37.bin': baseline, 'candidate-1.1.38.bin': factory, 'README.txt': instructions().encode(), 'source-pins.json': encoded(PINS)})
    archive(a.output/(PREFIX+'-Preserving-Update-From-1.1.37.zip'), kit)
    evidence = {'source-pins.json': encoded(PINS), 'native-baseline.json': (DOCS/'native-baseline.json').read_bytes(),
                'firmware.bin': firmware, 'firmware.elf': elf, 'default.elf': current['default.elf'], 'default.json': current['default.json'],
                'native-custody.json': encoded(custody), 'composition.json': encoded(composition), 'preservation.json': encoded(proof),
                'admission.json': encoded(admissions['normal']), 'admission-sanitized.json': encoded(admissions['sanitized']),
                'qualification.json': encoded(qualification), 'store-SHA256SUMS.txt': checksums(current), 'release.json': encoded(metadata)}
    for name in qualification['reports']: evidence['qualification/'+name+'.log'] = (a.qualification/(name+'.log')).read_bytes()
    for index in (1, 2): evidence['qualification/build-'+str(index)+'.json'] = (a.qualification/('build-'+str(index))/'build.json').read_bytes()
    archive(a.output/(PREFIX+'-Evidence.zip'), evidence)
    (a.output/'RELEASE-NOTES.txt').write_text('- Renders every Home watch face directly at the display’s native resolution.\n- Keeps native-size face transitions, boot effects, gestures and fast wake together.\n- Preserves the previous native SDR and app launch fixes.\n')
    (a.output/'UPDATE-INSTRUCTIONS.txt').write_text(instructions())
    (a.output/'SHA256SUMS').write_bytes(checksums(files(a.output)))
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__': main()
