#!/usr/bin/env python3
"""Prove policy-disabled LoRa reproduces both the predecessor and selected ELF."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

from compact_current_elf import compact
from build_lora_policy import clean, git, require, compile_exact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'baseline-system', 'baseline-utilities', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    args = parser.parse_args()
    record = json.loads((args.build / 'lora_messages-build-record.json').read_text())
    roots = record['source_roots']
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    clean(args.baseline_system, '7fb13b09b4dac275a8111b224784f8a472f39264')
    clean(args.baseline_utilities, 'e85eff650e9f748ae162fb725fb6e14eb6df876a')
    for owner in ('system-apps', 'utilities'):
        clean(Path(roots[owner]), record['sources'][owner])
    normalizer_path = Path(roots['utilities']) / 'scripts/normalize_xtensa_relocations.py'
    require(sha(normalizer_path) == 'f71d9ca3b267166bc69d0e4853463774a8dde5384924132e1aca0e0c2f3a965f', 'Normalizer changed')
    spec = importlib.util.spec_from_file_location('lora_flagoff_normalizer', normalizer_path)
    normalizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(normalizer)
    results = {}
    attempts = {}
    with tempfile.TemporaryDirectory(prefix='lora-policy-flagoff-') as temporary:
        for label in ('predecessor', 'candidate'):
            generated = Path(temporary) / label
            generated.mkdir()
            system = args.baseline_system if label == 'predecessor' else Path(roots['system-apps'])
            utilities = args.baseline_utilities if label == 'predecessor' else Path(roots['utilities'])
            mappings = [(roots['system-apps'], str(system)), (roots['utilities'], str(utilities)),
                        (roots['generated'], str(generated))]
            def mapped(value):
                for before, after in mappings:
                    value = value.replace(before, after)
                return value
            for name in ['exports.map', *record['generated_provenance']]:
                destination = generated / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(mapped((args.build / name).read_text()))
            command = [mapped(value) for value in record['command'] if value != '-DPORTABLE_TEXT_INPUT_POLICY']
            elf = generated / 'lora_messages.elf'
            attempts[label] = compile_exact(command, elf, args.output.parent / ('flagoff-' + label + '-linker-attempts'))
            normalizer.normalize(elf)
            compact(elf, command[0], debug_path=generated / 'lora_messages-debug.elf')
            results[label] = {'sha256': sha(elf), 'bytes': elf.stat().st_size}
    for owner in ('system-apps', 'utilities'):
        clean(Path(roots[owner]), record['sources'][owner])
    report = dict(schema='lora.modal-policy.flagoff-target.v1', device='watch',
        passed=results['predecessor'] == results['candidate'], targets=results, linker_attempts=attempts,
        selected_lora_0114_sha256=record['predecessor_elf_sha256'],
        selected_lora_0114_byte_equal=results['candidate']['sha256'] == record['predecessor_elf_sha256'],
        sources=record['sources'], baseline_system=git(args.baseline_system, 'rev-parse', 'HEAD'),
        baseline_utilities=git(args.baseline_utilities, 'rev-parse', 'HEAD'),
        only_removed_flag='-DPORTABLE_TEXT_INPUT_POLICY', hardware_verified=False, target_instructions_executed=False)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    require(report['passed'] and report['selected_lora_0114_byte_equal'],
            'Policy-disabled target differs from predecessor or selected LoRa 0.1.14')


if __name__ == '__main__':
    main()
