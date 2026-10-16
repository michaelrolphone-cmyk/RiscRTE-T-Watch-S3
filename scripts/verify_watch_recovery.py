#!/usr/bin/env python3
"""Admit the exact recovered T-Watch baseline; no build, upload or flash."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from read_only_spiffs import read_image
from watch_factory_appdata import require, sha, verify

ROOT = Path(__file__).resolve().parents[1]
SELECTION = json.loads((ROOT / 'docs/watch-recovery/selection.json').read_text())


def audit(raw, previous=None):
    s = SELECTION
    require(len(raw) == s['full_image_bytes'] and sha(raw) == s['full_image_sha256'], 'Wrong recovered full image')
    appdata = verify(raw)
    require(sha(raw[0x8000:0x9000]) == s['partition_table_sha256'], 'Partition table changed')
    bootfs, bank = raw[0x2f0000:0x800000], raw[0xff2000:0xff4000]
    require(sha(bootfs) == s['bootfs_sha256'] and sha(bank) == s['bank_state_sha256'], 'Paired component changed')
    files = read_image(bootfs, 0x510000)
    inventory = {n: dict(bytes=len(v), sha256=sha(v)) for n, v in sorted(files.items())}
    require(inventory == s['files'], 'Recovered complete inventory differs')
    require(len(files) == 113 and sum(n.endswith('.elf') for n in files) == 55, 'Incomplete cohort')
    cohort = json.loads(files['cohort.json'])
    require(cohort['version'] == '1.1.21' and cohort['product'] == 'twatch-s3' and
            cohort['source_revision'] == s['cohort_source_is_assembly_recipe'], 'Cohort identity differs')
    firmware = raw[0x10000:0x10000 + s['firmware']['bytes']]
    require(sha(firmware) == cohort['firmware_sha256'] == s['firmware']['sha256'] and
            len(firmware) == cohort['firmware_size'], 'Native component changed')
    fields = struct.unpack('<6I32s32sII', bank[:96])
    require(fields[:6] == (0x314b4252, 1, 0, len(firmware), len(bootfs), 2) and
            fields[6] == hashlib.sha256(firmware).digest() and fields[7] == hashlib.sha256(bootfs).digest() and
            fields[8] == 0 and fields[9] == zlib.crc32(bank[:92]) & 0xffffffff and
            bank[96:] == b'\xff' * (len(bank) - 96), 'Paired identity/hash/CRC differs')
    if previous is not None:
        require(sha(previous) == s['prior_full_image_sha256'], 'Wrong delivered predecessor')
        old = read_image(previous[0x2f0000:0x800000], 0x510000)
        require(set(old) == set(files) and [n for n in old if old[n] != files[n]] == ['cohort.json'],
                'Previously delivered app, provider, font or manifest changed')
        for start, end in [(0, 0x10000), (0x800000, 0xff2000), (0xff4000, 0x1000000)]:
            require(raw[start:end] == previous[start:end], 'Unrelated flash region changed')
    # SPIFFS formats lookup-page magic even in otherwise free physical blocks.
    empty = sum(bootfs[i:i + 30] == b'\xff' * 30 and
                bootfs[i + 256:i + 4096] == b'\xff' * (4096 - 256)
                for i in range(0, len(bootfs), 4096))
    require(empty >= s['minimum_free_spiffs_blocks'], 'SPIFFS reserve below floor')
    return dict(package_revision=s['package_revision'], full_image_sha256=sha(raw),
                native_source=s['firmware']['source'], compiled_home_source=s['compiled_home_source'],
                files=len(files), elfs=55, free_spiffs_blocks=empty, appdata=appdata,
                predecessor_checked=previous is not None, all_app_bytes_preserved=previous is not None,
                source_attribution='cohort.source_revision identifies assembly tooling; native source is recorded separately',
                host_mount_test='Run verify_factory_appdata_mount.py separately; byte admission alone is not mount proof',
                no_device_operation=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', required=True, type=Path)
    p.add_argument('--previous', type=Path)
    a = p.parse_args()
    print(json.dumps(audit(a.image.read_bytes(), a.previous.read_bytes() if a.previous else None), indent=2))


if __name__ == '__main__':
    main()
