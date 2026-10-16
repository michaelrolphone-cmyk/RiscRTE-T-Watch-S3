#!/usr/bin/env python3
"""Prove policy-disabled Spectrum reproduces both the predecessor and selected ELF."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

from compact_current_elf import compact
from build_spectrum_policy import clean, git, require, compile_exact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'baseline-system', 'baseline-utilities', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    args = parser.parse_args()
    record = json.loads((args.build / 'audio_spectrum-build-record.json').read_text())
    roots = record['source_roots']
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    clean(args.baseline_system, '7fb13b09b4dac275a8111b224784f8a472f39264')
    clean(args.baseline_utilities, '82d17d0d902d427938af95aae0e976c8f78041ed')
    for owner in ('system-apps', 'utilities'):
        clean(Path(roots[owner]), record['sources'][owner])
    normalizer_path = Path(roots['utilities']) / 'scripts/normalize_xtensa_relocations.py'
    require(sha(normalizer_path) == 'f71d9ca3b267166bc69d0e4853463774a8dde5384924132e1aca0e0c2f3a965f', 'Normalizer changed')
    spec = importlib.util.spec_from_file_location('spectrum_flagoff_normalizer', normalizer_path)
    normalizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(normalizer)
    results = {}
    attempts = {}
    with tempfile.TemporaryDirectory(prefix='spectrum-policy-flagoff-') as temporary:
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
            elf = generated / 'audio_spectrum.elf'
            attempts[label] = compile_exact(command, elf, args.output.parent / ('flagoff-' + label + '-linker-attempts'))
            normalizer.normalize(elf)
            compact(elf, command[0], debug_path=generated / 'audio_spectrum-debug.elf')
            results[label] = {'sha256': sha(elf), 'bytes': elf.stat().st_size}
    for owner in ('system-apps', 'utilities'):
        clean(Path(roots[owner]), record['sources'][owner])
    report = dict(schema='spectrum.modal-policy.flagoff-target.v1', device='watch',
        passed=results['predecessor'] == results['candidate'], targets=results, linker_attempts=attempts,
        selected_spectrum_054_sha256=record['predecessor_elf_sha256'],
        selected_spectrum_054_byte_equal=results['candidate']['sha256'] == record['predecessor_elf_sha256'],
        sources=record['sources'], baseline_system=git(args.baseline_system, 'rev-parse', 'HEAD'),
        baseline_utilities=git(args.baseline_utilities, 'rev-parse', 'HEAD'),
        only_removed_flag='-DPORTABLE_TEXT_INPUT_POLICY', hardware_verified=False, target_instructions_executed=False)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    require(report['passed'] and report['selected_spectrum_054_byte_equal'],
            'Policy-disabled target differs from predecessor or selected Spectrum 0.5.4')


if __name__ == '__main__':
    main()
