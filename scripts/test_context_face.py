#!/usr/bin/env python3
from pathlib import Path
import os,subprocess
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parents[1];out=root/'dist/context-face';out.mkdir(parents=True,exist_ok=True)
for san in (False,True):
    flags=['-std=c11','-DWATCH_CONTEXTS_CLIENT','-O1','-Wall','-Wextra','-Werror',*['-I'+str(root/p) for p in ('sdk/app','sdk/driver','include','.')]]
    if san:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie']
    binary=out/f'test-{int(san)}'
    subprocess.run([os.environ.get('CC','cc'),*flags,str(root/'tests/watch_context_face_test.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary),str(out)],check=True)
sheet=Image.new('RGB',(4*250,2*270),'black');draw=ImageDraw.Draw(sheet)
for i,label in enumerate(['Off','Loading','Paused','Audio','RF','Ambiguous','Malformed labels','Stale after pause']):
    data=(out/f'context-{i}.rgb565').read_bytes();rgb=bytearray()
    for j in range(0,len(data),2):
        v=data[j]|data[j+1]<<8;rgb.extend(((v>>11)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
    frame=Image.frombytes('RGB',(240,240),bytes(rgb));frame.save(out/f'context-{i}.png')
    x=i%4*250;y=i//4*270;sheet.paste(frame,(x,y));draw.text((x+10,y+246),label,fill='white')
sheet.save(out/'context-states.png')
