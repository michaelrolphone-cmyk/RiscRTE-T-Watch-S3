#!/usr/bin/env python3
import argparse,json,os,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--points',action='store_true');p.add_argument('--watch',required=True,type=Path);p.add_argument('--runtime',required=True,type=Path);p.add_argument('--utilities',required=True,type=Path);p.add_argument('--system-apps',required=True,type=Path);a=p.parse_args()
w,r,u,s=[x.resolve() for x in [a.watch,a.runtime,a.utilities,a.system_apps]];here=Path(__file__).resolve().parent;b=w/('dist/points-cross-layer' if a.points else 'dist/alarm-cross-layer');b.mkdir(parents=True,exist_ok=True)
overlay=b/'sdk-overlay';overlay.mkdir(exist_ok=True)
for folder in [w/'sdk/app',w/'sdk/driver']:
 for header in folder.glob('*.h'):
  if not any((r/'sdk'/part/header.name).exists() for part in ['app','driver','hardware']):(overlay/header.name).write_bytes(header.read_bytes())
inc=['-I'+str(x) for x in [here,w,w/'include',r/'sdk/app',r/'sdk/driver',r/'sdk/hardware',overlay,s/'lib/PortableApps/include',u/'lib/Alarm/include']]
san=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer'] if os.environ.get('SANITIZE')=='1' else []
def run(cmd):subprocess.run(list(map(str,cmd)),check=True)
for name,source,extra in [('sleep',here/'sleep_provider.c',[]),('rtc',here/'dependencies.c',['-DKIND=1']),('haptic',here/'dependencies.c',['-DKIND=2']),('audio',here/'dependencies.c',['-DKIND=3']),('alarm',u/'Services/alarm_service/service.c',['-DPOINTS_IN_TIME_SERVICE','-DPORTABLE_RTC_UTC8_DENVER'] if a.points else []),('default',here/'app.c',[])]:
 run(['cc',*san,'-std=c11','-Wall','-Wextra','-Werror','-fPIC','-fvisibility=hidden','-shared',*inc,*extra,source,'-o',b/(name+'.elf')])
run(['c++',*san,'-no-pie','-std=c++17','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-rdynamic',*(['-DPOINTS_CROSS_LAYER'] if a.points else []),*inc,*['-I'+str(x) for x in [r/'src',r/'lib/ArduinoJson/src',r/'test/drivers/stubs']],*[r/x for x in ['src/bootstrap/Json.cpp','src/bootstrap/Board.cpp','src/bootstrap/Runtime.cpp','src/runtime/drivers/ProviderGraphV2.cpp','src/runtime/drivers/ProviderModuleV2.cpp','src/ports/esp32s3/CpuPort.cpp']],here/'host.cpp','-ldl','-o',b/'test'])
def save(name,data):(b/name).write_text(json.dumps(data,indent=2)+'\n')
save('board.json',{'schema':'riscrte.board-hardware','schema_version':1,'board_id':'test','revision':'unspecified','buses':[],'devices':[{'instance_id':7,'chip':{'vendor':'test','model':'gpio','revision':'unspecified'},'compatible':'test,gpio','config_type':'gpio.bank','config_version':1,'config':{'pins':[7,6],'active_high':True,'pull_up':True,'debounce_us':0,'long_press_us':0,'click_min_us':0}}]})
for name,cap,api in [('sleep','test.sleep',1),('rtc','rtc.clock',2),('haptic','haptic.effect',1),('audio','audio.output',1)]:
 m={'type':'driver','id':name+'-test','version':'1.0.0','driver_abi':2,'architecture':'xtensa-esp32s3','file_name':name+'.elf','requires':[],'provides':[{'capability':cap,'api':api}]}
 if name=='sleep':m.update(requires=[{'capability':'hardware.device','api':1},{'capability':'platform.gpio','api':1}],hardware_compatibility=[{'compatible':'test,gpio','revisions':['unspecified'],'config_type':'gpio.bank','config_version':1}])
 save(name+'.json',m)
m=json.loads((u/('Services/alarm_service/points-manifest.json' if a.points else 'Services/alarm_service/manifest.json')).read_text());m['file_name']='alarm.elf';save('alarm.json',m)
save('default.json',{'type':'application','id':'sleep-review','version':'1.0.0','architecture':'xtensa-esp32s3','file_name':'default.elf','entry':'app_main','requires':[{'capability':'test.sleep','api':1},{'capability':'alarm.service','api':1}]})
keys=[{'key':k,'namespace':ns,'access':access} for k,ns,access in [('alarm_cfg',3,'read'),('timer_cfg',3,'read'),('alarm_occ',4,'read-write'),('timer_occ',4,'read-write'),('alert_mode',1,'read')]]
if a.points:keys += [{'key':'points_cfg','namespace':5,'access':'read'},{'key':'points_occ','namespace':4,'access':'read-write'}]
save('boot.json',{'board':'board.json','default_app':'default.elf','drivers':[{'manifest':'sleep.json','instance_id':7},*({'manifest':n+'.json'} for n in ['rtc','haptic','audio']),{'manifest':'alarm.json','key_value':keys}],'app_capabilities':[{'manifest':'default.json','grants':[{'capability':'test.sleep','api':1,'instance_id':7},{'capability':'alarm.service','api':1,'instance_id':0}]}]})
for mode in ['old-order','direct-refusal','crown-after-hold','hybrid-refusal','native-return','unhold-retained','resume-spi-error']:run([b/'test',b,mode])
