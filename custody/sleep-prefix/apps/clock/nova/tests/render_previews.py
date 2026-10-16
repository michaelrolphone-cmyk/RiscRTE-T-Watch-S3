#!/usr/bin/env python3
"""Render truthful, explicitly labeled host fixtures and reference comparisons."""
from pathlib import Path
import subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'dist/nova-tests/previews'
OUT.mkdir(parents=True,exist_ok=True)
exe=ROOT/'dist/nova-tests/frame'
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',12)
def render(args,name):
    raw=subprocess.check_output([str(exe),*args]);a=np.frombuffer(raw,dtype='<u2').reshape(240,240)
    rgb=np.stack((((a>>11)&31)*255//31,((a>>5)&63)*255//63,(a&31)*255//31),axis=-1).astype('uint8')
    im=Image.fromarray(rgb);im.save(OUT/(name+'.png'));return im
cases=[([], 'fixture-84', '10:42 AM / fixture 84%'),(['unknown'],'unknown','10:42 AM / battery unknown'),(['zero'],'zero','10:42 AM / real 0%'),(['unset'],'unset','RTC unset / fixture 84%'),(['midnight'],'midnight','12:00 AM / midnight'),(['noon'],'noon','12:00 PM / noon')]
proof=Image.new('RGB',(780,560),'#202328');d=ImageDraw.Draw(proof)
for i,(args,name,label) in enumerate(cases):
    x=(i%3)*260+10;y=(i//3)*280+30
    proof.paste(render(args,name),(x,y));d.text((x,y-22),label,font=font,fill='white')
proof.save(OUT/'edge-cases.png')
# Caller supplies the inspected reference raster, never fabricate a browser image.
if len(sys.argv)>2:
    reference=Image.open(sys.argv[2]).convert('RGB');comparison=Image.new('RGB',(500,286),'#202328');d=ImageDraw.Draw(comparison)
    comparison.paste(reference,(5,37));comparison.paste(Image.open(OUT/'fixture-84.png'),(255,37))
    d.text((8,5),'SOURCE SVG / design placeholders',font=font,fill='white')
    d.text((8,20),'Offline raster, exact fonts',font=font,fill='#adb8c0')
    d.text((258,5),'ACTUAL C / test battery input 84%',font=font,fill='white')
    d.text((258,20),'12-hour AM + honest RTC label',font=font,fill='#adb8c0')
    comparison.resize((1000,572)).save(OUT/'reference-vs-actual.png')
frames=[]
for ms in range(0,3000,100):
    frames.append(render(['phase',str(15000+ms),str(ms)],f'animation-{ms:04d}'))
frames[0].save(OUT/'animation-phases.gif',save_all=True,append_images=frames[1:],duration=100,loop=0)
print(OUT)
