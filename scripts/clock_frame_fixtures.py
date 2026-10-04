#!/usr/bin/env python3
"""Render reproducible expected frames with production code, not a second renderer."""
import hashlib,json,os,struct,subprocess,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'dist/clock-frames';out.mkdir(parents=True,exist_ok=True)
exe=out/'render-fixture'
subprocess.run([os.environ.get('CC','clang'),'-std=c11','-Wall','-Wextra','-Werror',
 '-I'+str(ROOT/'sdk/driver'),'-I'+str(ROOT/'include'),'-I'+str(ROOT),
 str(ROOT/'apps/clock/nova/nova.c'),str(ROOT/'tests/clock_frame_fixture.c'),'-o',str(exe)],check=True)
def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
frames=[]
for mode in ('valid','unset'):
 data=subprocess.check_output([str(exe),mode]);(out/(mode+'.rgb565')).write_bytes(data)
 scan=bytearray()
 for y in range(240):
  scan.append(0)
  for x in range(240):
   p=int.from_bytes(data[(y*240+x)*2:(y*240+x+1)*2],'little')
   scan.extend((((p>>11)&31)*255//31,((p>>5)&63)*255//63,(p&31)*255//31))
 png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',240,240,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b'')
 (out/(mode+'.png')).write_bytes(png)
 frames.append({'scenario':mode,'rtc':{'year':2028,'month':2,'day':29,'weekday':2,'hour':12,'minute':34,'second':0} if mode=='valid' else None,'renderer':'NOVA-7', 'hour_format':12, 'rtc_basis':'UTC+08', 'display_zone':'America/Denver', 'battery_valid':False, 'animation_ms':18250, 'subsecond_ms':250,'format':'RGB565 little-endian','width':240,'height':240,'stride_bytes':480,'sha256':hashlib.sha256(data).hexdigest(),'path':mode+'.rgb565'})
(out/'expected.json').write_text(json.dumps({'schema':1,'frames':frames},indent=2)+'\n')
print(json.dumps(frames,indent=2))
