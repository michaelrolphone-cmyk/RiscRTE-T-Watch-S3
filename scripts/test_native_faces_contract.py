#!/usr/bin/env python3
"""Reject any successor changes beyond Home code/version and product identity."""
import argparse, copy, json
from pathlib import Path
from watch_native_faces import PINS, encoded, files, need, require_final, verify_baseline, verify_metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-store', 'store', 'firmware'): parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-revision', required=True); a = parser.parse_args()
    require_final(); before = files(a.baseline_store); after = files(a.store); firmware = a.firmware.read_bytes()
    verify_baseline(before); verify_metadata(before, after, firmware, a.source_revision)
    cases = 0
    def reject(candidate, native=firmware):
        nonlocal cases
        try: verify_metadata(before, candidate, native, a.source_revision)
        except ValueError: cases += 1
        else: raise ValueError('Unexpected mutation accepted')
    for name in before:
        candidate = copy.deepcopy(after); candidate[name] += b'!'; reject(candidate)
    for key in ('requires', 'id', 'launcher_visible', 'version'):
        candidate = copy.deepcopy(after); manifest = json.loads(candidate['default.json']); manifest[key] = [] if key == 'requires' else 'changed'
        candidate['default.json'] = encoded(manifest); reject(candidate)
    candidate = copy.deepcopy(after); candidate['injected.json'] = b'{}'; reject(candidate)
    candidate = copy.deepcopy(after); del candidate['boot.json']; reject(candidate)
    reject(after, firmware+b'!')
    print('PASS:', cases, 'scope/authority/native mutation rejections; 118 preserved files')


if __name__ == '__main__': main()
