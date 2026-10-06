"""Exact current PMU custody without rewriting a delivered historical baseline."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUSTODY_PATH = 'scripts/pmu-sleep-custody.json'
SOURCE_PATHS = {'drivers/twatch_pmu/driver.c', 'drivers/twatch_pmu/manifest.json'}
SOURCE_ROOT = 'custody/sleep-prefix'
PMU_FILES = {'pmu/driver.elf', 'pmu/manifest.json'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def current_pmu_custody(root=ROOT):
    value = json.loads((root / CUSTODY_PATH).read_text())
    require(value['schema'] == 1 and set(value['source_sha256']) == SOURCE_PATHS and
            set(value['files']) == PMU_FILES, 'Unexpected PMU custody scope')
    for path, expected in value['source_sha256'].items():
        require(sha((root / SOURCE_ROOT / path).read_bytes()) == expected, 'PMU source differs from target custody: ' + path)
    manifest = json.loads((root / SOURCE_ROOT / 'drivers/twatch_pmu/manifest.json').read_text())
    package = value['package']
    require(package['id'] == 'twatch-pmu' and package['instance_id'] == 4 and
            package['kind'] == 'driver' and package['architecture'] == 'xtensa-esp32s3' and
            package['version'] == manifest['version'] == '0.5.3' and
            package['archive'] == 'driver-twatch-pmu-0.5.3-xtensa-esp32s3.rte.zip',
            'Unexpected PMU target identity')
    data = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
    require(value['files']['pmu/manifest.json'] == {'size_bytes': len(data), 'sha256': sha(data)},
            'PMU deployed manifest custody differs')
    return value


def current_driver_packages(baseline, root=ROOT):
    """Replace only the one historical PMU row; every other row stays exact."""
    packages = copy.deepcopy(baseline['driver_packages'])
    indices = [i for i, row in enumerate(packages) if row['id'] == 'twatch-pmu']
    require(len(indices) == 1 and packages[indices[0]]['instance_id'] == 4,
            'Historical PMU membership differs')
    packages[indices[0]] = current_pmu_custody(root)['package']
    return packages


def verify_current_pmu(files, root=ROOT):
    custody = current_pmu_custody(root)
    require(json.loads(files['shared/pmu-sleep-custody.json']) == custody,
            'Archived PMU custody differs from reviewed source')
    for name, expected in custody['files'].items():
        data = files['store/' + name]
        require({'size_bytes': len(data), 'sha256': sha(data)} == expected,
                'Current PMU payload differs: ' + name)
    package = custody['package']
    raw = files['packages/' + package['archive']]
    require(len(raw) == package['size_bytes'] and sha(raw) == package['sha256'],
            'Current PMU package differs')
