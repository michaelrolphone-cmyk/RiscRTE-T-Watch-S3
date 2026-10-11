#!/usr/bin/env python3
"""Build only Buttons 0.1.22 against the unchanged Watch 1.1.0 canvas pins.

This creates a candidate ELF and source receipt, not a qualified product BIN.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

from build_contexts_cohort import Compiler, definitions, write_catalog
from build_current_apps import application_inputs

W = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
for name in ('system', 'utilities', 'runtime', 'output'):
    p.add_argument('--' + name, type=Path, required=True)
p.add_argument('--cc', required=True)
a = p.parse_args()
profile = json.loads((W / 'apps/canvas-profile.json').read_text())
repos = {'system-apps': a.system.resolve(), 'utilities': a.utilities.resolve(),
         'runtime': a.runtime.resolve()}
pins = {'system-apps': 'watch-system', 'utilities': 'utilities', 'runtime': 'runtime'}
for label, repo in repos.items():
    expected = profile['sources'][pins[label]]
    for ref, field in [('HEAD', 'commit'), ('HEAD^{tree}', 'tree')]:
        assert subprocess.check_output(['git', '-C', str(repo), 'rev-parse', ref], text=True).strip() == expected[field], label
    assert not subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain', '--untracked-files=no']), label
U = repos['utilities']
assert json.loads((U / 'Apps/ble_buttons.json').read_text())['version'] == '0.1.22'
# Source already contains the fix; prove ancestry instead of relabeling old code.
subprocess.run(['git', '-C', str(U), 'merge-base', '--is-ancestor',
                'e620160c48c11fb074378cd31a20ff8362a9659b', 'HEAD'], check=True)
out = a.output.resolve()
out.mkdir(parents=True, exist_ok=False)
write_catalog(out, [])
c = Compiler(a.cc, W, out, repos, W)
sources, includes, allowed = application_inputs('ble_buttons', U / 'Apps/ble_buttons.c', repos, W, out, 'runtime-features')
includes += [U / 'lib/Contexts/include']
raw, receipt = c.build('ble_buttons', sources, definitions('ble_buttons', '0.1.22', W),
                       includes, {'app_main', 'app_module_init', 'app_module_fini'}, allowed)
receipt.update(version='0.1.22', source_pins=profile['sources'],
               watch_commit=subprocess.check_output(['git', '-C', str(W), 'rev-parse', 'HEAD'], text=True).strip(),
               hardware_tested=False, whole_cohort_qualified=False)
(out / 'build.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(receipt['sha256'], len(raw))
