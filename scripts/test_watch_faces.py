#!/usr/bin/env python3
from pathlib import Path
import subprocess,os
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'dist/watch-faces';out.mkdir(parents=True,exist_ok=True)
subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all',*['-I'+str(ROOT/p) for p in ('sdk/app','sdk/driver','include','.')],str(ROOT/'tests/watch_faces_test.c'),str(ROOT/'apps/clock/nova/nova.c'),'-o',str(out/'test')],check=True)
subprocess.run([str(out/'test'),str(out)],check=True)
from PIL import Image,ImageDraw
faces=Image.new('RGB',(1020,1620),'black');picker=Image.new('RGB',(1020,1620),'black')
for i,name in enumerate(('NOVA','ANALOG','RADAR','HEX','TERMINAL','MINIMAL','BINARY','CHRONO','AURORA','HORIZON','GIANT','MOON','TOPO','ORRERY','FLIP','MATRIX','GRID','RIBBON','YEAR','24H','AGENDA','DATE','DOTS','PROGRESS')):
 for prefix,sheet in [('face',faces),('picker',picker)]:
  b=(out/f'{prefix}-{i}.rgb565').read_bytes();rgb=[]
  for j in range(0,len(b),2):
   v=b[j]|b[j+1]<<8;rgb.extend(((v>>11)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
  im=Image.frombytes('RGB',(240,240),bytes(rgb));im.save(out/f'{prefix}-{i}.png');sheet.paste(im,(i%4*255,i//4*270));ImageDraw.Draw(sheet).text((i%4*255+80,i//4*270+250),name,fill='white')
faces.save(out/'native-faces.png');picker.save(out/'native-pickers.png')

# These 96 golden frames were rendered by the delivered0.6.0 source before
# optimizing. Preserve approved pixels at RTC phases, fractional scroll and
# enlarged selection-pulse edges, not just an isolated static screenshot.
import ctypes,hashlib,json
source=str(ROOT/'tests/watch_faces_work_test.c')
flags=['-std=c11','-O2','-Wall','-Wextra','-Werror',*['-I'+str(ROOT/p) for p in ('sdk/app','sdk/driver','include','.')]]
cc=os.environ.get('CC','cc')
subprocess.run([cc,*flags,'-fsanitize=undefined','-fno-sanitize-recover=all',source,'-o',str(out/'work-test')],check=True)
subprocess.run([str(out/'work-test')],check=True,timeout=30)
subprocess.run([cc,*flags,'-shared','-fPIC',source,'-o',str(out/'raster-test.so')],check=True)
lib=ctypes.CDLL(str(out/'raster-test.so'));pixels=ctypes.create_string_buffer(115200)
for case in json.loads((ROOT/'tests/watch_faces_raster_golden.json').read_text()):
 lib.render_sample(pixels,case['id'],case['ms'],case['picker'],case['position'],case['scale'])
 assert hashlib.sha256(pixels.raw).hexdigest()==case['sha256'],case
print('96 delivered0.6.0 face/picker frames remain byte-identical')

subprocess.run([cc,*flags,'-fsanitize=undefined','-fno-sanitize-recover=all',str(ROOT/'tests/watch_face_categories_test.c'),'-o',str(out/'category-test')],check=True)
subprocess.run([str(out/'category-test')],check=True)

subprocess.run([cc,*flags,'-fsanitize=undefined','-fno-sanitize-recover=all',str(ROOT/'tests/watch_face_division_test.c'),str(ROOT/'apps/clock/effects/divdi3.c'),'-o',str(out/'division-test')],check=True)
subprocess.run([str(out/'division-test')],check=True)

# Translated production rows are byte-exact crops of the individual pages.
subprocess.run([cc,*flags,'-fsanitize=undefined','-fno-sanitize-recover=all',str(ROOT/'tests/watch_face_vertical_render_test.c'),'-o',str(out/'vertical-test')],check=True)
subprocess.run([str(out/'vertical-test'),str(out)],check=True)
vertical=Image.new('RGB',(1020,1350),'black')
offsets=[48,0,-1,-24,-60,-90,-120,-150,-180,-216,-239,-240,-264,-720,-768,-840,-900,-959,-960,-1008]
for i,offset in enumerate(offsets):
 b=(out/f'vertical-{i:02}.rgb565').read_bytes();rgb=[]
 for j in range(0,len(b),2):
  v=b[j]|b[j+1]<<8;rgb.extend(((v>>11)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
 im=Image.frombytes('RGB',(240,240),bytes(rgb));im.save(out/f'vertical-{i:02}.png');vertical.paste(im,(i%4*255,i//4*270));ImageDraw.Draw(vertical).text((i%4*255+70,i//4*270+250),f'Offset {offset}px',fill='white')
vertical.save(out/'vertical-motion.png')
