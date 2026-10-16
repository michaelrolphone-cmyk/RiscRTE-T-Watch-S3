#!/usr/bin/env python3
"""Preserve the released native Watch feature and storage selections."""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads((ROOT / 'profiles/native-idf61-baseline.json').read_text())
    profile = (ROOT / 'profiles/native-idf61.cmake').read_text()
    expected = {flag[2:] for flag in baseline['flags']
                if re.fullmatch(r'-DRISC_[A-Z0-9_]+=\d+', flag)}
    expected.remove('RISC_RUNTIME_METADATA_PSRAM=1')  # shared native selection
    actual = set(re.findall(r'\bRISC_[A-Z0-9_]+=\d+\b', profile))
    assert actual == expected, {'missing': expected - actual, 'extra': actual - expected}
    assert not any(x.startswith('RISC_NATIVE_SETTINGS_') for x in actual)
    assert 'RISC_NATIVE_EXTRA_SOURCES' not in profile
    assert 'RISC_NATIVE_TARGET "esp32s3-16mb-appdata-expanded-iq"' in profile
    assert 'RISC_NATIVE_APPDATA ON' in profile and 'RISC_NATIVE_IQ ON' in profile
    for flag in baseline['flags']:
        if flag.startswith('-Wl,-u,'):
            assert '"' + flag + '"' in profile, flag
    partitions = 'partitions-paired-appdata-expanded.csv'
    released = subprocess.check_output(['git', '-C', str(args.runtime), 'show',
        baseline['source_runtime_revision'] + ':' + partitions])
    assert (args.runtime / partitions).read_bytes() == released
    with tempfile.TemporaryDirectory() as tmp:
        runner = Path(tmp) / 'check.cmake'
        runner.write_text('set(RISC_PRODUCT_PROFILE "' + str(ROOT / 'profiles/native-idf61.cmake') + '")\n'
            'set(CMAKE_BINARY_DIR "' + tmp + '")\n'
            'include("' + str(args.runtime.resolve() / 'idf/product-profile.cmake') + '")\n')
        subprocess.run(['cmake', '-P', str(runner)], check=True)
    print('Native T-Watch profile preserves released features, providers and partitions PASS')

if __name__ == '__main__':
    main()
