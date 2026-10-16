#!/usr/bin/env python3
"""Set the reviewed clean Runtime 0.1.53 commit once; never publish or build."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from current_apps_overlay import ROOT, encoded, require
from power_repair_profile import RUNTIME_VERSION, runtime_requirements


def pin(runtime, expected_sha, root=ROOT, *, replace_reviewed_sha=None):
    runtime, root = Path(runtime).resolve(), Path(root).resolve()
    require(re.fullmatch('[0-9a-f]{40}', expected_sha) is not None, 'Exact reviewed Runtime SHA required')
    from power_watch_candidate import checked_source
    checked_source(runtime, expected_sha)
    version = subprocess.check_output(['git', '-C', str(runtime), 'show', 'HEAD:platformio.ini'], text=True)
    require(re.search(r'^version\s*=\s*' + re.escape(RUNTIME_VERSION) + r'\s*$', version, re.M),
            'Reviewed Runtime must be version ' + RUNTIME_VERSION)
    requirements = runtime_requirements(root, allow_pending=True)
    profile_path = root / 'apps/power-repair-sources.json'
    profile = json.loads(profile_path.read_text())
    if replace_reviewed_sha is not None:
        require(re.fullmatch('[0-9a-f]{40}', replace_reviewed_sha) is not None, 'Exact previous reviewed Runtime SHA required')
        require(requirements['source_sha'] == profile['sources']['runtime']['commit'] == replace_reviewed_sha,
                'Previous reviewed Runtime pin differs')
        trees = [subprocess.check_output(['git', '-C', str(runtime), 'rev-parse', revision + '^{tree}'], text=True).strip()
                 for revision in (replace_reviewed_sha, expected_sha)]
        require(trees[0] == trees[1], 'Replacement Runtime is not the reviewed same tree')
        requirements['source_sha'] = expected_sha;profile['sources']['runtime']['commit'] = expected_sha
    require(requirements['source_sha'] in (None, expected_sha) and
            profile['sources']['runtime']['commit'] in (None, expected_sha), 'Power Runtime is already pinned to another source')
    requirements['source_sha'] = expected_sha;profile['sources']['runtime']['commit'] = expected_sha
    (root / 'apps/power-repair-runtime-requirements.json').write_bytes(encoded(requirements))
    profile_path.write_bytes(encoded(profile))
    print('Pinned clean reviewed Runtime', expected_sha, 'No build or publication performed.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--expected-sha', required=True)
    p.add_argument('--replace-reviewed-sha', help='Explicit previously reviewed pin; replacement must have the identical Git tree')
    a = p.parse_args();pin(a.runtime, a.expected_sha, replace_reviewed_sha=a.replace_reviewed_sha)
