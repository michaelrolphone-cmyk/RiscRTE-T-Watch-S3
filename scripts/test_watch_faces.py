#!/usr/bin/env python3
from pathlib import Path
import subprocess,os
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'dist/watch-faces';out.mkdir(parents=True,exist_ok=True)
subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all',*['-I'+str(ROOT/p) for p in ('sdk/app','sdk/driver','include','.')],str(ROOT/'tests/watch_faces_test.c'),str(ROOT/'apps/clock/nova/nova.c'),'-o',str(out/'test')],check=True)
subprocess.run([str(out/'test'),str(out)],check=True)
from PIL import Image,ImageDraw
faces=Image.new('RGB',(1020,540),'black');picker=Image.new('RGB',(1020,540),'black')
for i,name in enumerate(('NOVA','ANALOG','RADAR','HEX','TERMINAL','MINIMAL','BINARY','CHRONO')):
 for prefix,sheet in [('face',faces),('picker',picker)]:
  b=(out/f'{prefix}-{i}.rgb565').read_bytes();rgb=[]
  for j in range(0,len(b),2):
   v=b[j]|b[j+1]<<8;rgb.extend(((v>>11)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
  im=Image.frombytes('RGB',(240,240),bytes(rgb));im.save(out/f'{prefix}-{i}.png');sheet.paste(im,(i%4*255,i//4*270));ImageDraw.Draw(sheet).text((i%4*255+80,i//4*270+250),name,fill='white')
faces.save(out/'native-faces.png');picker.save(out/'native-pickers.png')
