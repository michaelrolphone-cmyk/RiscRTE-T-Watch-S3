#!/usr/bin/env python3
"""Inspect target entry frames and bounded static Scanner modal storage."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from build_scanner_policy import require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    record = json.loads((args.build / 'ble_scanner-build-record.json').read_text())
    elf = args.build / 'ble_scanner.elf'
    debug = args.build / 'debug/ble_scanner.elf'
    prefix = record['command'][0].removesuffix('gcc')
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    require(sha(elf) == record['sha256'], 'Target ELF custody differs')
    nm = subprocess.check_output([prefix + 'nm', '-S', str(debug)], text=True).splitlines()
    functions = {}
    for line in nm:
        columns = line.split()
        if len(columns) == 4 and columns[2] in 'tT':
            functions.setdefault(int(columns[0], 16), []).append(columns[3])
    frames = {}
    disassembly = subprocess.check_output([prefix + 'objdump', '-d', str(debug)], text=True)
    for line in disassembly.splitlines():
        match = re.match(r'^\s*([0-9a-f]+):.*\bentry\s+a1,\s*(0x[0-9a-f]+|[0-9]+)', line)
        if match and int(match[1], 16) in functions:
            for name in functions[int(match[1], 16)]:
                key = name if name not in frames else name + '@0x' + match[1]
                require(key not in frames, 'Duplicate target frame')
                frames[key] = int(match[2], 0)
    normalize = lambda name: re.sub(r'\$(?:lto_priv|constprop|isra|part)\$\d+', '', name)
    modal = {name: frame for name, frame in frames.items() if normalize(name).startswith(
        ('name_', 'portable_text_client_', 'portable_text_checkpoint_', 'portable_text_adapter_policy_', 'portable_app_before_'))
        or name in ('begin_name', 'save_name', 'app_main', 'app_module_init', 'app_module_fini')}
    symbols = {}
    expected = {'name_state': 88, 'name_client': 48, 'name_checkpoint': 8, 'name_policy_continuity': 1, 'editing': 25}
    for line in nm:
        columns = line.split()
        if len(columns) != 4:
            continue
        address, size, kind, name = columns
        name = normalize(name)
        if name in expected:
            require(name not in symbols, 'Duplicate modal storage')
            symbols[name] = {'bytes': int(size, 16), 'symbol_kind': kind, 'static_storage': kind in 'bBdD',
                             'address': int(address, 16)}
    require({name: row['bytes'] for name, row in symbols.items()} == expected and
            all(row['static_storage'] for row in symbols.values()), 'Modal storage size or placement changed')
    require('app_main' in frames and modal['app_main'] <= 512 and all(frame <= 512 for frame in modal.values()),
            'Modal target frame regression')
    result = dict(schema='scanner.target-stack.v1', device=record['device'], application_source=record['sources']['utilities'],
        system_source=record['sources']['system-apps'], target_elf_sha256=sha(elf), debug_elf_sha256=sha(debug),
        method='Actual target disassembly entry a1 operands; no target instructions executed',
        entry_frames_bytes=modal, maximum_modal_frame_bytes=max(modal.values()),
        all_entry_frames_maximum_bytes=max(frames.values()), static_modal_storage=symbols,
        bounded_custom_name_capacity_bytes=25, per_frame_regression_checks_passed=True,
        peak_call_chain_stack_usage_proven=False,
        limits=['Inlining folds helper frames into callers; absent symbols are not separate frame measurements.',
                'Entry frame sizes do not prove dynamic call-chain peak stack use, Runtime allocation, or physical execution.'])
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
