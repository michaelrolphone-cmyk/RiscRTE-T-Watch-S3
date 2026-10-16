#!/usr/bin/env python3
"""Verify strict source replay without modifying expected digests or recipes."""
import io, json
from pathlib import Path
from elftools.elf.elffile import ELFFile
from watch_launch_brightness import PINS, HANDOFF, clean, files, need, sha
from package_app_repair import link_evidence


def verify_replay(root, source, compiler):
    clean(source, PINS['producer_revision'])
    need(sha(compiler.read_bytes()) == PINS['compiler_sha256'], 'Wrong pinned compiler')
    report = json.loads((root/'receipt.json').read_text())
    need(report['product'] == 'twatch' and report['source_inputs_verified'] is True and report['hardware_tested'] is False, 'Wrong replay identity')
    need(set(report['apps']) == set(HANDOFF['apps']), 'Incomplete replay')
    need(report['driver_sha256'] == sha((source/'scripts/replay_shared_crash_apps.py').read_bytes()), 'Replay producer differs')
    need(report['compiler_sha256'] == PINS['compiler_sha256'], 'Replay compiler differs')
    spec = source/'docs/shared-app-crashes/replay'
    need(report['spec_sha256'] == {p.name:sha(p.read_bytes()) for p in sorted(spec.iterdir()) if p.is_file()}, 'Replay specs differ')
    inputs = json.loads((spec/'inputs.json').read_text())
    need(report['repositories'] == inputs['repositories'], 'Replay source revisions differ')
    need(report['repositories']['r0']['commit'] == PINS['adapter_revision'], 'Adapter source differs')
    recipes = json.loads((spec/'twatch.json').read_text())
    need(set(recipes) == set(HANDOFF['apps']), 'Wrong producer recipe set')
    for name,row in report['apps'].items():
        payload = (root/(name+'.elf')).read_bytes(); expected = HANDOFF['apps'][name]
        need(row['sha256'] == recipes[name]['sha256'] == expected['sha256'] == sha(payload), 'Replay app digest differs: '+name)
        need(row['bytes'] == recipes[name]['bytes'] == expected['bytes'] == len(payload), 'Replay app size differs: '+name)
        elf = ELFFile(io.BytesIO(payload)); symbols = elf.get_section_by_name('.dynsym')
        actual = {'imports':sorted(s.name for s in symbols.iter_symbols() if s.name and s['st_shndx']=='SHN_UNDEF'),
                  'exports':sorted(s.name for s in symbols.iter_symbols() if s.name and s['st_shndx']!='SHN_UNDEF')}
        need(actual == row['symbols'] == recipes[name]['symbols'] == expected['symbols'], 'Replay symbols differ: '+name)
        log = (root/(name+'.log')).read_bytes()
        need(log == (root/Path(row['link_attempts'][-1]['log']).parent.name/Path(row['link_attempts'][-1]['log']).name).read_bytes(), 'Final build log differs')
    link_evidence(root, report)
    return report
