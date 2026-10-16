#!/usr/bin/env python3
"""Real HID apps + production adapter + Nova pixels over copied peripheral APIs."""
import argparse,os,subprocess,gzip
from pathlib import Path
ROOT=None
HERE=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument("--utilities",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument('--system-apps',required=True,type=Path);p.add_argument('--paper',action='store_true');p.add_argument('--watch',type=Path,help='Link the production Watch FT6336U driver over simulated I2C reports');p.add_argument('--runtime',type=Path,help='Link the production Runtime serial logger with its existing USB host shim');p.add_argument('--watch-touch-source',type=Path,help='Explicit Watch touch source, relative to --watch (defaults to the current provider if present)');p.add_argument('--low-battery',action='store_true',help='Use the delivered low-battery lifecycle policy');p.add_argument('--scene',action='append',help='Run only the named scene (repeatable)');a=p.parse_args();ROOT=a.utilities.resolve();system=a.system_apps.resolve();watch=a.watch.resolve() if a.watch else None
if a.watch_touch_source and not watch:p.error('--watch-touch-source requires --watch')
touch_source=(watch/a.watch_touch_source if a.watch_touch_source else watch/'drivers/current/twatch_touch/driver.c') if watch else None
if watch and not a.watch_touch_source and not touch_source.is_file():touch_source=watch/'drivers/twatch_touch/driver.c'
scenes={
 'idle':([],[]),
 'back-top':([(30,20,20)],['BACK']),
 'back-top-active':([(3,50,218),(30,20,20)],['ACTIVE','BACK']),
 'reconnect':([(3,50,218)],['ACTIVE']),
 'left-tap':([(3,50,218),(30,100,120)],['ACTIVE','MOUSE']),
 'tap-drag':([(3,50,218),(30,100,120),(32,100,120),(33,114,120),(34,128,120)],['ACTIVE','TAP_DRAG']),
 'scroll-x':([(3,50,218),(30,80,115),(30,140,115),(31,96,116),(31,156,116),(32,112,115),(32,172,115)],['ACTIVE','SCROLL_X']),
 'scroll-y':([(3,50,218),(30,80,115),(30,140,115),(31,81,127),(31,141,127),(32,80,139),(32,140,139)],['ACTIVE','SCROLL_Y']),
 'scroll-free':([(3,50,218),(30,80,115),(30,140,115),(31,92,122),(31,152,122),(32,104,129),(32,164,129)],['ACTIVE','SCROLL_FREE']),
 'right-tap':([(3,50,218),(30,100,120),(30,180,120)],['ACTIVE','MOUSE']),
 'keys':([(3,50,218),(30,40,160),(31,40,160),(32,40,160)],['ACTIVE','KEYS']),
 'pair-accept':([(3,180,218),(10,50,76),(30,180,218)],['ACTIVE','PAIR','PAIR_ACCEPT']),
 'pair-reject':([(3,180,218),(10,50,76),(30,50,218)],['ACTIVE','PAIR','PAIR_REJECT']),
 'pair-move':([(3,180,218),(10,50,76),(30,180,218),(31,160,218),(60,180,218)],['ACTIVE','PAIR','PAIR_ACCEPT','PAIR_RECOVERED','PAIR_MOVED']),
 'pair-multitouch':([(3,180,218),(10,50,76),(30,180,218),(30,160,218),(60,180,218)],['ACTIVE','PAIR','PAIR_ACCEPT','PAIR_RECOVERED','PAIR_MULTITOUCH']),
 'pair-gap':([(3,180,218),(10,50,76),(38,180,218),(39,180,218),(40,180,218),(60,180,218)],['ACTIVE','PAIR','PAIR_ACCEPT','PAIR_RECOVERED','GAP']),
 'disconnect':([(3,50,218),(30,40,160),(31,40,160)],['ACTIVE','DISCONNECT']),
 'mouse-reconnect':([(3,50,218),(30,100,120),(31,110,120),(62,100,120),(80,100,120)],['ACTIVE','MOUSE','MOUSE_RECONNECT']),
 'transport-reconnect':([(3,50,218),(30,100,120),(31,110,120),(60,50,218),(80,100,120)],['ACTIVE','MOUSE','TRANSPORT_RECONNECT']),
 'low-battery':([(3,50,218)],['ACTIVE','LOW_BATTERY']),
 'sleep':([(3,50,218)],['ACTIVE','SLEEP']),
 'alarm':([(3,50,218),(38,40,160),(39,40,160),(60,120,166)],['ACTIVE','ALARM']),
 'raw-gap':([(3,50,218),(38,40,160),(39,40,160),(40,40,160),(41,40,160)],['ACTIVE','GAP']),
 'back':([(3,50,218),(30,20,20)],['ACTIVE','BACK']),
 'nested-back':([(3,180,218),(10,30,207),(20,120,174),(30,20,20),(40,20,20),(50,20,20)],['BACK']),
 'quick-controls':([(3,50,218),(30,120,5),(31,120,60),(32,120,140),(90,120,222)],['ACTIVE','QUICK']),
 'cleanup':([(3,50,218),(30,20,20)],['ACTIVE','BACK','CLEANUP']),
 'home':([(3,50,218)],['ACTIVE','HOME']),
 'raw-home':([(3,50,218)],['ACTIVE','HOME','RAW_HOME']),
 'edit-home':([(3,180,218),(10,30,207),(20,205,124)],['HOME','UNSAVED']),
 'edit-cancel':([(3,180,218),(10,30,207),(20,205,124),(60,50,218)],['UNSAVED']),
 'save-retry':([(3,180,218),(10,30,207),(20,205,124),(60,180,218),(80,180,218)],['SAVED','SAVE_FAIL']),
 'edit-save':([(3,180,218),(10,30,207),(20,205,124),(30,120,172),(40,40,75),(50,20,20),(60,180,218)],['SAVED']),
}
if a.paper:
 scenes['quick-controls']=([(3,110,732),(30,200,20),(31,200,100),(90,240,620),(91,240,560)],['ACTIVE','QUICK'])
 scenes['quick-edit']=([(3,348,732),(10,100,530),(20,405,345),(30,200,20),(31,200,100),(90,240,620),(91,240,560),(110,348,732)],['SAVED'])
 def paper_actions(scene,actions):
  if scene in ('quick-controls','quick-edit'):return actions
  result=[]
  for n,x,y in actions:
   if x==20 and y==20:px,py=60,(50 if scene in ('back-top','back-top-active') else 88)
   elif y==207:px,py=100,530
   elif y==174 or y==172:px,py=200,475
   elif y==124 and x==205:px,py=405,345
   elif y==75:px,py=100,220
   elif y==76:px,py=(100 if x<116 else 340),220
   elif y==218:px,py=(110 if x<116 else 348 if x==180 else 308),732
   else:px,py=32+(x-8)*416//224,224+(y-80)*400//110
   result.append((n,px,py))
  return result
 scenes={name:(paper_actions(name,actions),checks) for name,(actions,checks) in scenes.items()}
 # Alarm acknowledgement belongs to the adapter's 480x800 modal.
 scenes['alarm']=(scenes['alarm'][0][:-1]+[(60,240,650)],scenes['alarm'][1])
if not a.low_battery:del scenes['low-battery']
if a.scene:
 unknown=set(a.scene)-scenes.keys()
 if unknown:p.error('Unknown scenes: '+', '.join(sorted(unknown)))
 scenes={name:scene for name,scene in scenes.items() if name in a.scene}
# FT6336U is touch-only; raw-home is an impossible controller button report.
# Keep real navigation Home and all touch gestures. Do not fabricate a button.
if watch:del scenes['raw-home']
scenes={'second-contact-reject': ([(3,50,218),(30,120,5),(31,120,60),(31,170,100),(32,120,60),(32,170,100)],['ACTIVE'])}
for san in (False,True):
 for name in ('ble_touchpad','ble_buttons'):
  out=a.output.resolve()/str(int(san))/name;out.mkdir(parents=True,exist_ok=True)
  wrapper=out/'adapter_observed.c';wrapper.write_text('#include "'+str(system/'lib/PortableApps/src/adapter.c')+'"\n'+'bool qualification_quick_visible(void){return pqa_visible(&quick.ui); }\n')
  catalog=out/'catalog.c';catalog.write_text('#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[1]={{.compatible=false}};\nconst unsigned portable_catalog_count=0;\n')
  flags=['-DPORTABLE_NOVA_UI','-DPORTABLE_APP_OWNS_TOUCH_CHROME','-DPORTABLE_RADIO_SESSION','-DPORTABLE_ALARM_CLIENT','-DPORTABLE_FORCE_FULL_FRAMES','-DPORTABLE_APP_SLEEP_LOCAL','-DPORTABLE_INPUT_NAVIGATION','-DPORTABLE_INPUT_NAVIGATION_LOCAL','-DPORTABLE_QUICK_ACTIONS','-DPORTABLE_QUICK_RADIOS','-DPORTABLE_RETURN_APP="springboard.elf"']
  flags+=['-DPORTABLE_PAPER_HID','-DPORTABLE_HOME_APP="default.elf"']
  if a.paper:
   flags.remove('-DPORTABLE_QUICK_RADIOS');flags.remove('-DPORTABLE_FORCE_FULL_FRAMES');flags+=['-DHID_RENDER_PAPER','-DPORTABLE_DISPLAY_ROTATION=90']
  if a.low_battery:flags+=['-DPORTABLE_LOW_BATTERY']
  if san:flags+=['-fsanitize='+os.environ.get('HID_SANITIZERS','address,undefined'),'-fno-sanitize-recover=all','-fno-omit-frame-pointer']
  exe=out/'renderer';sources=[HERE/'test/watch_second_contact_app_test.c',ROOT/'Apps'/f'{name}.c',out/'adapter_observed.c',catalog]+[system/'lib/PortableApps/src'/s for s in ['quick_actions.c','quick_render.c','quick_session.c','quick_radios.c']]
  extra=[]
  if watch:
   flags+=['-DHID_RENDER_WATCH_TOUCH']
   extra=['-I'+str(watch/'sdk/driver'),'-I'+str(watch/'include')]
   # The physical provider's headers include their own provider ABI locally.
   # Compile these translation units against only Watch SDK headers, keeping
   # the app/adapter's separate System ABI copy out of their include search.
   for index,source in enumerate([ROOT/'test/native_apps/hid_watch_touch_backend.c',touch_source]):
    obj=out/f'watch-touch-{index}.o'
    subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O1','-g','-Wall','-Wextra','-Werror',*flags,*extra,'-c',str(source),'-o',str(obj)],check=True)
    sources.append(obj)
   extra=[]
  if a.runtime:
   runtime=a.runtime.resolve();flags+=['-DHID_RENDER_RUNTIME_DIAGNOSTICS']
   for index,source in enumerate([ROOT/'test/native_apps/hid_runtime_diagnostics.cpp',runtime/'src/ports/esp32s3/SleepDiagnostics.cpp']):
    obj=out/f'diagnostics-{index}.o'
    subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-DRISC_SLEEP_DIAGNOSTICS=1',*flags,'-I'+str(runtime/'src'),'-I'+str(runtime/'test/diagnostic_shim'),'-c',str(source),'-o',str(obj)],check=True)
    sources.append(obj)
  # Resolve shared application ABI headers from the System adapter first. A
  # separate Watch SDK copy is not the same file for #pragma once, even when
  # its bytes match; checkout timestamps must not determine host compilation.
  subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O1','-g','-Wall','-Wextra','-Werror',*flags,*['-I'+str(i) for i in [system/'Apps',ROOT/'Apps',ROOT/'lib/Bluetooth/include',system/'lib/PortableApps/include',system/'lib/NativeApps/include']],*extra,*map(str,sources),*(['-lstdc++'] if a.runtime else []),'-o',str(exe)],check=True)
  for scene,(actions,checks) in scenes.items():
   if name=='ble_touchpad' and scene in ('keys','nested-back','edit-save','edit-home','edit-cancel','save-retry','quick-edit'):continue
   if name=='ble_buttons' and scene in ('left-tap','right-tap','mouse-reconnect','transport-reconnect','tap-drag','scroll-x','scroll-y','scroll-free'):continue
   folder=out/scene;folder.mkdir(exist_ok=True)
   for f in folder.glob('frame-*.*'):f.unlink()
   path=folder/'actions.txt';path.write_text(''.join(f'{n} {x} {y}\n' for n,x,y in actions));env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',**{'HID_RENDER_'+c:'1' for c in checks})
   subprocess.run([str(exe),str(folder),str(path)],check=True,env=env,timeout=30)
   frames=sorted(folder.glob('frame-*.*'));assert frames,scene
   for frame in frames:
    raw=frame.read_bytes();header=b'P4\n480 800\n' if a.paper else b'P6\n240 240\n255\n';assert raw.startswith(header) and len(raw)==len(header)+(480*800//8 if a.paper else 240*240*3)
    packed=frame.with_suffix(frame.suffix+'.gz');packed.write_bytes(gzip.compress(raw,mtime=0));assert gzip.decompress(packed.read_bytes())==raw;frame.unlink()
print('Full Watch adapter coherent-report second-contact rejection checks passed normally and under '+os.environ.get('HID_SANITIZERS','address,undefined'))
