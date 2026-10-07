#!/usr/bin/env python3
"""Set the pending RF Utilities pin from a clean completed immutable checkout."""
import argparse
import json
from pathlib import Path
import subprocess

from current_apps_overlay import ROOT, UTILITY_APPS, config, encoded, require
from rf_spectrum_profile import accepted_configuration, validate_waterfall_manifest


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def pin_utilities(utilities, root=ROOT):
    utilities, root = Path(utilities).resolve(), Path(root).resolve()
    c = config(root, profile='rf-spectrum', allow_pending=True)
    head = git(utilities, 'rev-parse', 'HEAD')
    require(not git(utilities, 'status', '--porcelain', '--untracked-files=no'),
            'Final Utilities checkout has tracked changes')
    require(c['sources']['utilities']['commit'] in (None, head),
            'RF source is already pinned; a different source requires a reviewed profile change')
    accepted = accepted_configuration(root)['sources']['utilities']['commit']
    require(subprocess.run(['git', '-C', str(utilities), 'merge-base', '--is-ancestor', accepted, head],
                           capture_output=True).returncode == 0,
            'Final Utilities source must retain accepted 1.0.7 fixes')
    for name in UTILITY_APPS:
        manifest = json.loads((utilities / 'Apps' / (name + '.json')).read_text())
        require(manifest['version'] == c['source_app_versions'][name],
                'Final Utilities manifest version differs: ' + name)
    manifest = json.loads((utilities / 'Apps/waterfall.json').read_text())
    validate_waterfall_manifest(manifest)
    c['sources']['utilities']['commit'] = head
    from rf_spectrum_profile import validate_configuration
    validate_configuration(c, root)
    (root / 'apps/rf-spectrum-sources.json').write_bytes(encoded(c))
    require(config(root, profile='rf-spectrum') == c, 'RF final source pin readback differs')
    return head


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--utilities', type=Path, required=True)
    args = parser.parse_args()
    print('Pinned RF Utilities source: ' + pin_utilities(args.utilities))
