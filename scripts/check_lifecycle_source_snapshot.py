#!/usr/bin/env python3
"""Check the public Watch18 files against restored original source commits."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'docs/lifecycle/watch-1.0.18'
record = json.loads((BASE / 'source-custody.json').read_bytes())
bundle = BASE / record['bundle']['file']
assert record['schema'] == 1 and record['dependency_sources_included'] is False
assert record['provisioning_payloads_included'] is False and record['separate_model_header_or_provisioning_payloads_included'] is False
assert bundle.stat().st_size == record['bundle']['size_bytes']
assert hashlib.sha256(bundle.read_bytes()).hexdigest() == record['bundle']['sha256']
subprocess.run(['git', '-C', str(ROOT), 'bundle', 'verify', str(bundle)], check=True)
subprocess.run(['git', '-C', str(ROOT), 'fetch', str(bundle),
                'refs/watch-custody/1.0.18/*:refs/watch-custody/1.0.18/*'], check=True)
for item in record['heads'].values():
    actual = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', item['bundle_ref']], text=True).strip()
    assert actual == item['commit']
    actual_tree = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', actual + '^{tree}'], text=True).strip()
    assert actual_tree == item['tree']
for name, ref in record['selected_source_files'].items():
    expected = subprocess.check_output(['git', '-C', str(ROOT), 'show', record['heads'][ref]['commit'] + ':' + name])
    path = ROOT / name
    assert path.is_file() and not path.is_symlink() and path.read_bytes() == expected, name
for name, digest in record['target_watch_inputs'].items():
    path = ROOT / name
    assert path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
print('Original Watch18 history, selected source files and target Watch inputs match')
