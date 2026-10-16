#!/usr/bin/env python3
"""Admit every installed ELF with the unchanged production native firmware."""
import argparse, json, os, subprocess, sys
from pathlib import Path
from watch_launch_brightness import ROOT, PINS, clean, need, sha, encoded, files, verify_baseline, verify_metadata, verify_wake
from verify_app_repair_native import composition, scheduler_proof
import check_runtime_store_admission as admission


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'store', 'baseline-store', 'compiler', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args(); a.runtime = a.runtime.resolve()
    clean(a.runtime, PINS['runtime_revision'])
    native = a.runtime / '.pio/build/watch-native-ui/firmware.elf'
    active = files(a.baseline_store); store = files(a.store); verify_wake(store)
    need(store['boot.json'] == active['boot.json'], 'Boot authority changed')
    verify_baseline(active)
    verify_metadata(active, store, (native.parent/'firmware.bin').read_bytes(), json.loads(store['cohort.json'])['source_revision'])
    admission.native_composition = composition
    try:
        result = admission.admit_cohort(a.runtime, native.read_bytes(), active, store,
                                       app_policy_rows=32, native_profile=a.runtime / 'watch-native-ui.ini')
    except subprocess.CalledProcessError as error:
        print(error.stdout or '', file=sys.stderr); print(error.stderr or '', file=sys.stderr)
        raise
    need(result['elf_count'] == 59 and result['hardware_calls'] == result['storage_calls'] == 0, 'Incomplete/stateful admission')
    result.update(sanitized=os.environ.get('SANITIZE') == '1', producer_sha256=sha(Path(__file__).read_bytes()))
    result['iq_scheduler'] = scheduler_proof(native, a.compiler)
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / 'admission.json').write_bytes(encoded(result))
    print('PASS: all 59 ELFs admitted; Home manifest authority preserved; no hardware/storage I/O')


if __name__ == '__main__': main()
