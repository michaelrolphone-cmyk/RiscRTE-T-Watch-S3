#!/usr/bin/env python3
"""Reuse the exact pinned SPIFFS pack/independent-unpack implementation."""
import argparse
import json
from pathlib import Path
from audio_deployment import ROOT,PROFILE,require,verify
from build_wifi_store import build
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--mkspiffs',type=Path,required=True);p.add_argument('--output',type=Path,default=ROOT/'dist/audio-common');a=p.parse_args()
    require(verify(a.archive)['profile']==PROFILE,'Only verified common audio store may be packed')
    print(json.dumps(build(a.archive,a.mkspiffs,a.output,verify_archive=verify),indent=2))
