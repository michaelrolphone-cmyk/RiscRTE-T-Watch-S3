#!/usr/bin/env python3
"""Check the current shared Home ABI and serial progress requirements.

Source selection checks accompany, and do not replace, linked native and runtime
behavioral tests. This does not execute Xtensa instructions or access hardware.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def require(value, message):
    if not value:
        raise ValueError(message)


def qualify(runtime, watch):
    runtime, watch = Path(runtime), Path(watch)
    header = (runtime / 'sdk/app/RiscRuntimeV1.h').read_bytes()
    require(header == (watch / 'sdk/app/RiscRuntimeV1.h').read_bytes(), 'Exact shared Home Runtime ABI differs')
    require((runtime / 'sdk/app/RiscRuntimeSleepV1.h').read_bytes() ==
            (watch / 'sdk/app/RiscRuntimeSleepV1.h').read_bytes(), 'Exact sleep transaction ABI differs')
    source = (runtime / 'src/bootstrap/Runtime.cpp').read_text()
    for needle in ('currentRuntime->sleepPrepare(token)', 'currentRuntime->sleepResume(token)',
                   'port_.serialFilesControlCheckpoint()', 'return deferSerial();'):
        require(needle in source, 'Selected Runtime lacks current Home lifecycle support: ' + needle)
    confirm = source[source.index('bool Runtime::confirmBoot() {'):source.index('bool Runtime::appUpdate(')]
    require('providerStorageSafe() && (!port_.confirmBoot || port_.confirmBoot())' in confirm,
            'Paired confirmation storage safety veto changed')
    serial = (runtime / 'src/runtime/serial/Files.cpp').read_text()
    require('void Files::controlCheckpoint()' in serial and 'RISC_FILES_BUSY' in serial,
            'RAM-only control progress and bounded storage refusal required')
    with tempfile.TemporaryDirectory() as tmp:
        test = Path(tmp) / 'abi.c'
        test.write_text('#include <RiscRuntimeV1.h>\n#include <stddef.h>\n'
            '_Static_assert(offsetof(risc_runtime_api_v1,sleep_prepare)==RISC_RUNTIME_SERVICE_CHECKPOINT_V1_SIZE,"append-only prepare");\n'
            '_Static_assert(offsetof(risc_runtime_api_v1,sleep_resume)==offsetof(risc_runtime_api_v1,sleep_prepare)+sizeof(((risc_runtime_api_v1*)0)->sleep_prepare),"append-only resume");\n'
            'int main(void){return 0;}\n')
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-I'+str(runtime/'sdk/app'), str(test), '-o',str(Path(tmp)/'abi')],check=True)
        subprocess.run([str(Path(tmp)/'abi')],check=True)
    return {'abi_identical':True,'append_only_sleep_abi_compiles':True,
            'paired_confirmation_storage_veto_preserved':True,
            'serial_control_progress_selected':True,'hardware_tested':False,
            'scope':'ABI/source selection; separate normal/sanitized Runtime behavior and exact linked native checks are required',
            'sources':{name:hashlib.sha256((runtime/name).read_bytes()).hexdigest() for name in
                ('sdk/app/RiscRuntimeV1.h','sdk/app/RiscRuntimeSleepV1.h','src/bootstrap/Runtime.cpp','src/runtime/serial/Files.cpp')}}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--watch',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(qualify(args.runtime,args.watch),sort_keys=True,indent=2))
