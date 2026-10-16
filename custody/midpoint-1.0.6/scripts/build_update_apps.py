#!/usr/bin/env python3
"""Build the explicit paired Watch app/provider lane; never build firmware or flash."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from build_launcher_apps import ROOT, build as build_apps
from build_alarm_apps import build_service

MODES = {'paired': (), 'ota': ('ota_update',), 'all': ('ota_update', 'app_store')}
ICON_REFRESH_ELFS = {'springboard.elf','battery.elf','settings.elf','calculator.elf','stopwatch.elf',
                     'alarms.elf','countdown.elf','points_in_time.elf','wifi_settings.elf'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(system, utilities, runtime, productivity, updates=('ota_update', 'app_store')):
    updates = tuple(updates)
    if updates not in MODES.values():
        raise ValueError('Unknown staged updater selection')
    pins = json.loads((ROOT/'apps/update-sources.json').read_text())
    for name, repo in [('system-apps', system), ('utilities', utilities),
                       ('runtime', runtime), ('productivity', productivity)]:
        if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
                != pins[name]['commit'] or
                subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'],
                                        cwd=repo, text=True).strip()):
            raise ValueError('Clean exact update source required: ' + name)
    source_baseline = json.loads((ROOT/'scripts/update-service-source-baseline.json').read_text())
    if source_baseline['system_apps_source_sha'] != pins['system-apps']['commit']:
        raise ValueError('Provider source baseline is stale')
    for name, expected in source_baseline['source_sha256'].items():
        if sha((system/name).read_bytes()) != expected:
            raise ValueError('Pinned provider source changed: ' + name)
    for name, expected in source_baseline['application_manifest_sha256'].items():
        manifest_path = system/'Apps'/(name+'.json')
        if (sha(manifest_path.read_bytes()) != expected or
                json.loads(manifest_path.read_text())['version'] != source_baseline['application_versions'][name]):
            raise ValueError('Pinned application manifest changed: '+name)
    for header in ('RiscHttpClientV1.h', 'RiscBankStoreV1.h', 'RiscPlatformClockV1.h'):
        if ((system/'lib/PortableApps/include'/header).read_bytes()
                != (runtime/'sdk/driver'/header).read_bytes()):
            raise ValueError('Native provider API differs from exact Runtime: ' + header)
    build_apps(system, utilities, alarms=True, runtime=runtime,
               productivity=productivity, wifi=True, updates=updates)
    build_service(system, utilities, runtime, points=True, wifi=True, updates=True)
    out = ROOT/'dist/update-launcher'
    providers = {}
    if updates:
        env = dict(os.environ)
        if env.get('TWATCH_CC'):
            env['NATIVE_APP_CC'] = env['TWATCH_CC']
        provider_dir = out/'providers'
        subprocess.run([sys.executable, str(system/'scripts/build_portable_updates.py'),
                        '--services-only', '--rtc-utc-offset-seconds', '28800',
                        '--output-dir', str(provider_dir)], env=env, check=True)
        for app in updates:
            kind, short = ('firmware', 'update-fw') if app == 'ota_update' else ('apps', 'update-apps')
            source = provider_dir/('software-update-'+kind)
            record = json.loads((source/'build-record.json').read_text())
            if record['source_sha256'] != source_baseline['source_sha256']:
                raise ValueError('Provider build provenance differs from pinned source: '+kind)
            for source_name, target_name in [('driver.elf', short+'.elf'),
                                             ('manifest.json', short+'.json'),
                                             ('build-record.json', short+'-build.json')]:
                (out/target_name).write_bytes((source/source_name).read_bytes())
            providers[app] = {'kind': kind, 'path': short,
                              'sha256': sha((out/(short+'.elf')).read_bytes()),
                              'manifest_sha256': sha((out/(short+'.json')).read_bytes())}
    baseline = json.loads((ROOT/'scripts/update-preservation-baseline.json').read_text())
    preserved = {}
    mismatches = {}
    for path, expected in baseline['files'].items():
        if not path.endswith('.elf') or path == 'default.elf' or path in ICON_REFRESH_ELFS:
            continue
        artifact = 'alarm-service.elf' if path == 'alarm-service/driver.elf' else path
        if '/' in artifact:  # Physical drivers are independently pinned at deployment verification.
            continue
        data = (out/artifact).read_bytes()
        actual = {'size_bytes': len(data), 'sha256': sha(data)}
        if actual != expected:
            mismatches[path] = actual
        else:
            preserved[path] = expected
    if mismatches:
        raise ValueError('Update changed unrelated delivered executables: '+json.dumps(mismatches,sort_keys=True))
    runtime_requirements = json.loads((ROOT/'apps/update-runtime-requirements.json').read_text())
    record = {'schema': 1, 'apps': list(updates), 'source_pins': pins,
              'runtime_candidate_status': runtime_requirements['deployment']['candidate_artifact']['status'],
              'layout': 'riscrte-paired-16m-v1', 'store_abi': 1,
              'migration_only': True, 'rtc_utc_offset_seconds': 28800,
              'wifi_namespace': 6, 'wifi_instance': 15,
              'providers': providers, 'preserved_executables': preserved,
              'baseline_watch_source_sha': baseline['watch_source_sha']}
    (out/'update-build.json').write_text(json.dumps(record, indent=2)+'\n')
    print('Paired Watch lane:', ', '.join(updates) or 'health confirmation only',
          '; unrelated delivered app/service ELFs unchanged; no firmware or device operation')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system-apps', 'utilities', 'runtime', 'productivity'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--mode', choices=MODES, default=json.loads((ROOT/'apps/update-lane.json').read_text())['mode'])
    args = parser.parse_args()
    build(*(getattr(args, name).resolve() for name in
            ('system_apps', 'utilities', 'runtime', 'productivity')), updates=MODES[args.mode])
