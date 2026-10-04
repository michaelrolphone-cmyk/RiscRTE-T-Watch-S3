#!/usr/bin/env python3
"""Prove variant-neutral launcher store by comparing all eight explicit bundles."""
import argparse
from build_clock_common import build, ROOT
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--pr-head-sha',required=True)
a=p.parse_args()
r=build(sorted((ROOT/'dist/launcher-deployments').glob('*.zip')),ROOT/'dist/launcher-common',pr_head_sha=a.pr_head_sha,launcher=True)
print('Verified common launcher deployment:',r['archive'],r['sha256'])
