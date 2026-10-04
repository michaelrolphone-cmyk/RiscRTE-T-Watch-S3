#!/usr/bin/env python3
"""Compile production renderers, verify guards/semantics, export actual RGB565."""
from pathlib import Path
import os, subprocess, hashlib, json
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'dist/points-native';OUT.mkdir(parents=True,exist_ok=True)
CC=os.environ.get('CC','cc')
FLAGS=['-std=c11','-O2','-Wall','-Wextra','-Werror',*['-I'+str(ROOT/p) for p in ('sdk/app','sdk/driver','include','.')]]
SOURCE=ROOT/'tests/watch_faces_points_test.c'
subprocess.run([CC,*FLAGS,'-fsanitize=address,undefined','-fno-sanitize-recover=all',str(SOURCE),'-o',str(OUT/'test')],check=True)
subprocess.run([str(OUT/'test'),str(OUT)],check=True,timeout=120)
NAMES=('NEXT','RING','LADDER','DAYLINE','TRIPLE','STATUS','BOARD','WORKDAY','UP NEXT')
CASES=('configured fixture','empty','unavailable','service error','RTC unset','no work pair','next selected day +3D','DST fall-back input','midnight rollover','unknown battery','noon','midnight','24-hour policy','16 clustered ticks','stale projection error','unknown phase','overnight work','duration end BACK')
def decode(raw):
    rgb=bytearray()
    for i in range(0,len(raw),2):
        v=raw[i]|raw[i+1]<<8;rgb.extend(((v>>11)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
    return Image.frombytes('RGB',(240,240),bytes(rgb))
hashes={}
for scenario,label in enumerate(CASES):
    rows=(len(NAMES)+3)//4;sheet=Image.new('RGB',(1020,rows*270+30),'#080b0d');d=ImageDraw.Draw(sheet)
    d.text((12,8),'ACTUAL PRODUCTION C RGB565 | TEST INPUT: '+label,fill='white')
    for index,name in enumerate(NAMES):
        path=OUT/f'case-{scenario:02}-face-{index+24}.rgb565';raw=path.read_bytes();hashes[path.name]=hashlib.sha256(raw).hexdigest()
        frame=decode(raw);frame.save(path.with_suffix('.png'));x=index%4*255;y=index//4*270+30
        sheet.paste(frame,(x,y));d.text((x+80,y+246),name,fill='white')
    sheet.save(OUT/f'case-{scenario:02}-sheet.png')
(OUT/'frame-sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
# Determinism: renderer binaries and fixture pixels are host-produced, not SVG
# sketches or physical-watch captures. No source placeholder schedule compiled.
source=(ROOT/'apps/clock/faces/points_collection.inc').read_text()
for fake in ('STANDUP','REVIEW','GYM','84%'):
    assert fake not in source, fake
print(f'{len(CASES)*len(NAMES)} production frames and {len(CASES)} labeled sheets: {OUT}')
