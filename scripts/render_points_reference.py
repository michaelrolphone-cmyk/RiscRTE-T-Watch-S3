#!/usr/bin/env python3
"""Offline raster of owner-supplied HTML reference, using retained OFL fonts.

Reference placeholders are only a design fixture; never a firmware schedule.
Usage: render_points_reference.py /path/to/watchfaces-schedule.html
"""
from pathlib import Path
import json, os, re, subprocess, sys
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'dist/points-reference';OUT.mkdir(parents=True,exist_ok=True)
source=Path(sys.argv[1]).read_text()
script=re.search(r'<script>(.*?)</script>',source,re.S).group(1)
script=script[:script.index('const grid=')]
js='''const fs=require('fs'),vm=require('vm');let defs='';const box={document:{getElementById:()=>({insertAdjacentHTML:(position,value)=>{defs+=value;}})}};
vm.createContext(box);vm.runInContext('''+json.dumps(script)+'''+`\nthis.output=F.map(([name,draw])=>({name,svg:draw({d:new Date(2026,9,4,10,42,18),h:'10',m:'42',s:'18'})}));`,box,{timeout:1000});
process.stdout.write(JSON.stringify({defs,faces:box.output}));'''
result=json.loads(subprocess.check_output(['node','-e',js]))
fonts=ROOT/'apps/clock/nova/fonts'
conf=OUT/'fonts.conf';conf.write_text(f'<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir>{fonts}</dir><cachedir>{OUT}/font-cache</cachedir></fontconfig>')
env=dict(os.environ,FONTCONFIG_FILE=str(conf),XDG_CACHE_HOME=str(OUT/'cache'),XDG_CONFIG_HOME=str(OUT/'config'),TZ='UTC')
sheet=Image.new('RGB',(1020,570),'#080b0d');d=ImageDraw.Draw(sheet)
d.text((12,8),'OWNER HTML REFERENCE | illustrative schedule and battery | offline SVG/font raster',fill='white')
for i,face in enumerate(result['faces']):
    svg=OUT/f'reference-{i}.svg';png=svg.with_suffix('.png')
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240"><style>.f{fill:none}.o{font-family:Orbitron}.r{font-family:Rajdhani}.m{font-family:Share Tech Mono}</style><defs><filter id="g" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'+result['defs']+'</defs><rect width="240" height="240" fill="black"/>'+face['svg']+'</svg>')
    subprocess.run(['inkscape',str(svg),'--export-type=png',f'--export-filename={png}'],check=True,env=env,stdout=subprocess.DEVNULL)
    x=i%4*255;y=i//4*270+30;sheet.paste(Image.open(png).convert('RGB'),(x,y));d.text((x+80,y+246),face['name'],fill='white')
sheet.save(OUT/'reference-sheet.png')
native=ROOT/'dist/points-native/case-00-sheet.png'
if native.exists():
    comparison=Image.new('RGB',(2040,570),'black');comparison.paste(sheet,(0,0));comparison.paste(Image.open(native),(1020,0));comparison.save(OUT/'source-vs-production.png')
print(OUT/'reference-sheet.png')
