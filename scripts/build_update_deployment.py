#!/usr/bin/env python3
"""Package all eight explicit paired profiles; never create a flash image."""
import argparse
import json
from pathlib import Path
from build_clock_deployment import ROOT, build, encoded
from build_update_apps import MODES
from verify_update_deployment import verify


def build_all(root=ROOT, mode='all'):
    profiles = json.loads((root/'board.json').read_text())['profiles']
    if len(profiles) != 8 or len(set(profiles)) != 8:
        raise ValueError('Exactly eight explicit source profiles required')
    deployments = []
    for name in sorted(profiles):
        result = build(root/name, root=root, launcher=True, alarms=True, points=True,
                       wifi=True, updates=MODES[mode])
        verify(root/'dist/update-launcher-deployments'/result['archive'], root=root)
        deployments.append(result)
    catalog = {'schema': 1, 'mode': mode, 'apps': list(MODES[mode]), 'deployments': deployments}
    (root/'dist/update-launcher-deployments/catalog.json').write_bytes(encoded(catalog))
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=MODES, default=json.loads((ROOT/'apps/update-lane.json').read_text())['mode'])
    args = parser.parse_args()
    print(json.dumps(build_all(mode=args.mode), indent=2))
