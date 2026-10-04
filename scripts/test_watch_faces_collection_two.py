#!/usr/bin/env python3
"""Guarded production renders and optional offline supplied-SVG visual fixture."""
from pathlib import Path
import hashlib, os, subprocess, sys
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist/collection-two'
OUT.mkdir(parents=True, exist_ok=True)
reference = ROOT / 'apps/clock/faces/reference/Watch Faces II — 8 × 240×240.html'
assert len(reference.read_bytes()) == 13023
assert hashlib.sha256(reference.read_bytes()).hexdigest() == 'acee670c95c80ff8967ee1e10fea2aa1942220395f3a2cdc3036d68d7e350477'
flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined', '-fno-sanitize-recover=all']
flags += ['-I' + str(ROOT / p) for p in ('sdk/app', 'sdk/driver', 'include', '.')]
subprocess.run([os.environ.get('CC', 'cc'), *flags, str(ROOT / 'tests/watch_faces_collection_two_test.c'), '-o', str(OUT / 'test')], check=True)
subprocess.run([str(OUT / 'test'), str(OUT)], check=True)
names = ('AURORA', 'HORIZON', 'GIANT', 'MOON', 'TOPO', 'ORRERY', 'FLIP', 'MATRIX')
sheet = Image.new('RGB', (1020, 540), 'black')
for i, name in enumerate(names):
    raw = (OUT / f'face-{i}.rgb565').read_bytes()
    rgb = bytearray()
    for p in range(0, len(raw), 2):
        v = raw[p] | raw[p + 1] << 8
        rgb.extend(((v >> 11) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31))
    im = Image.frombytes('RGB', (240, 240), bytes(rgb))
    im.save(OUT / f'face-{i}.png')
    x, y = i % 4 * 255, i // 4 * 270
    sheet.paste(im, (x, y))
    ImageDraw.Draw(sheet).text((x + 80, y + 250), name, fill='white')
sheet.save(OUT / 'native-faces.png')
if '--reference' in sys.argv:
    # Evaluate only the inspected pure SVG-generating definitions. The sandbox
    # provides no browser, filesystem, fetch, network or animation-loop API.
    (OUT / 'render-reference.js').write_text(r'''
const fs=require('fs'),vm=require('vm');
const html=fs.readFileSync(process.argv[2],'utf8');let defs='';
const context={Math,Float32Array,performance:{now:()=>42000},document:{getElementById:()=>({insertAdjacentHTML:(_,s)=>defs+=s})}};
vm.createContext(context);vm.runInContext(html.split('<script>')[1].split('const now=')[0]+';this.faces=F;',context);
for(let phase=0;phase<2;phase++){
 context.performance.now=()=>42000+phase*10000;
 const d=new Date(2026,9,4,10,42,18,250);d.setMilliseconds(d.getMilliseconds()+phase*10000);
 const sf=18.25+phase*10,mf=42+sf/60,hf=10+mf/60,t={d,sf,mf,hf,h:'10',m:'42',dt:'SUN 04 OCT',day:4,blink:true};
 const style='<style>.f{fill:none}.o{font-family:Orbitron}.r{font-family:Rajdhani Medium}.r[font-weight="600"],.r[font-weight="700"]{font-family:Rajdhani SemiBold}.m{font-family:Share Tech Mono}</style>';
 fs.writeFileSync(process.argv[3]+`/reference-${phase}.svg`,`<svg xmlns="http://www.w3.org/2000/svg" width="1020" height="540"><rect width="1020" height="540" fill="black"/>${style}<defs>${defs}</defs>`+context.faces.map(([n,f],i)=>`<svg x="${i%4*255}" y="${Math.floor(i/4)*270}" width="240" height="240" viewBox="0 0 240 240">${f(t)}</svg><text x="${i%4*255+120}" y="${Math.floor(i/4)*270+257}" text-anchor="middle" fill="white" font-family="Rajdhani Medium" font-size="13">${n}</text>`).join('')+'</svg>');
}
''')
    conf = OUT / 'fonts.conf'
    conf.write_text(f'<fontconfig><dir>{ROOT}/apps/clock/nova/fonts</dir><cachedir>{OUT}/font-cache</cachedir></fontconfig>')
    env = dict(os.environ, TZ='UTC', FONTCONFIG_FILE=str(conf))
    subprocess.run(['node', str(OUT / 'render-reference.js'), str(reference), str(OUT)], check=True, env=env)
    for phase in range(2):
        subprocess.run(['inkscape', str(OUT / f'reference-{phase}.svg'), '-o', str(OUT / f'reference-{phase}.png')], check=True, env=env)
print('Collection II source hash and native contact sheet verified:', OUT)
