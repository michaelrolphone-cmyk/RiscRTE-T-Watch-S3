#!/usr/bin/env python3
"""Build both final paired Clocks against the same schema as the Points writer.

The historical update-custody Clock remains untouched. Its old decoder must
never accompany a newer writer/service in the installable combined image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from build_clock_app import ROOT, build as build_clock

FILES = ('default.elf', 'default.json', 'clock.elf', 'clock.json')

def sha(data):
    return hashlib.sha256(data).hexdigest()

def build(system, utilities, output):
    pins = json.loads((ROOT/'apps/points-sources.json').read_text())
    for name, path in (('system-apps', system), ('utilities', utilities)):
        actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain', '--untracked-files=no'], text=True).strip()
        if actual != pins[name]['commit'] or dirty:
            raise ValueError('Paired Points Clock requires clean pinned source: '+name)
    headers = {name: sha((utilities/'lib/Alarm/include'/name).read_bytes())
               for name in ('PointsRecords.h', 'PointsSchedule.h')}
    if b'#define POINTS_META_KEY ' not in (utilities/'lib/Alarm/include/PointsRecords.h').read_bytes():
        raise ValueError('Paired Points Clock requires current custom-type schema')
    output.mkdir(parents=True, exist_ok=True)
    records = {}
    for returning in (False, True):
        build_clock(launcher=True, returning=returning, alarm_system=system,
                    points_utilities=utilities, paired=True)
        name = 'clock' if returning else 'default'
        records[name] = json.loads((ROOT/'dist/update-launcher/build-record.json').read_text())
        for suffix in ('.elf', '.json'):
            (output/(name+suffix)).write_bytes((ROOT/'dist/update-launcher'/(name+suffix)).read_bytes())
    record = {'schema': 1, 'watch_source_sha': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
              'points_sources': pins, 'headers': headers, 'paired_boot_confirmation': True,
              'apps': records,
              'files': {name: {'sha256': sha((output/name).read_bytes()), 'size_bytes': (output/name).stat().st_size} for name in FILES}}
    (output/'points-paired-clock.json').write_text(json.dumps(record, indent=2)+'\n')
    return record

def verify(directory, head, service_build, root=ROOT):
    directory = Path(directory)
    record = json.loads((directory/'points-paired-clock.json').read_text())
    if record.get('schema') != 1 or record.get('watch_source_sha') != head or record.get('paired_boot_confirmation') is not True:
        raise ValueError('Paired Points Clock provenance mismatch')
    if record.get('points_sources') != json.loads((root/'apps/points-sources.json').read_text()):
        raise ValueError('Paired Clock and current Points source pins differ')
    if service_build.get('source_pins') != record['points_sources']:
        raise ValueError('Paired Clock and current Points service source pins differ')
    for name in ('PointsRecords.h', 'PointsSchedule.h'):
        if record['headers'].get(name) != service_build.get('points_headers', {}).get(name):
            raise ValueError('Paired Clock and current Points service schema differ: '+name)
    if set(record['files']) != set(FILES):
        raise ValueError('Paired Points Clock membership mismatch')
    files = {name: (directory/name).read_bytes() for name in FILES}
    for name, data in files.items():
        if record['files'][name] != {'sha256': sha(data), 'size_bytes': len(data)}:
            raise ValueError('Paired Points Clock content mismatch: '+name)
    return files, record

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-apps', required=True, type=Path)
    parser.add_argument('--utilities', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'dist/points-paired-clock')
    args = parser.parse_args()
    build(args.system_apps.resolve(), args.utilities.resolve(), args.output.resolve())
