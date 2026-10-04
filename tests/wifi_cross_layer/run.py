#!/usr/bin/env python3
"""Actual Runtime/CpuPort/provider/grant lifecycle, using synthetic RF hardware."""
import argparse,json,os,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--system-apps',type=Path,required=True);p.add_argument('--utilities',type=Path,required=True);a=p.parse_args()
w=Path(__file__).resolve().parents[2];r=a.runtime.resolve();s=a.system_apps.resolve();u=a.utilities.resolve();here=Path(__file__).resolve().parent;b=w/'dist/wifi-cross-layer';b.mkdir(parents=True,exist_ok=True)
san=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer'] if os.environ.get('SANITIZE')=='1' else []
incs=['-I'+str(x) for x in [here,w/'include',w/'drivers/twatch_wifi',r/'sdk/app',r/'sdk/driver',r/'sdk/hardware',w/'sdk/driver',s/'lib/PortableApps/include',u/'lib/Alarm/include',s/'lib/NativeApps/include']] 
def run(c):subprocess.run(list(map(str,c)),check=True)
for name,source in [('wifi',w/'drivers/twatch_wifi/driver.c'),('sleep',here/'sleep.c'),('default',here/'app.c'),('observer',here/'observer.c'),('consumer',here/'consumer.c')]:
 run(['cc',*san,'-std=c11','-Wall','-Wextra','-Werror','-fPIC','-fvisibility=hidden','-shared',*incs,source,'-o',b/(name+'.elf')])
for name,source,extra in [('rtc',w/'tests/alarm_cross_layer/dependencies.c',['-DKIND=1']),('haptic',w/'tests/alarm_cross_layer/dependencies.c',['-DKIND=2']),('audio',w/'tests/alarm_cross_layer/dependencies.c',['-DKIND=3']),('alarm',u/'Services/alarm_service/service.c',['-DPOINTS_IN_TIME_SERVICE','-DPORTABLE_RTC_UTC8_DENVER'])]:
 run(['cc',*san,'-std=c11','-Wall','-Wextra','-Werror','-fPIC','-fvisibility=hidden','-shared',*incs,*extra,source,'-o',b/(name+'.elf')])
run(['c++',*san,'-no-pie','-std=c++17','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-rdynamic',*incs,*['-I'+str(x) for x in [r/'src',r/'lib/ArduinoJson/src',r/'test/drivers/stubs']],*[r/x for x in ['src/bootstrap/Json.cpp','src/bootstrap/Board.cpp','src/bootstrap/Runtime.cpp','src/runtime/drivers/ProviderGraphV2.cpp','src/runtime/drivers/ProviderModuleV2.cpp','src/ports/esp32s3/CpuPort.cpp']],here/'host.cpp','-ldl','-o',b/'test'])
def save(n,d):(b/n).write_text(json.dumps(d,indent=2)+'\n')
board={'schema':'riscrte.board-hardware','schema_version':1,'board_id':'test','revision':'unspecified','buses':[],'devices':[
 {'instance_id':7,'chip':{'vendor':'test','model':'gpio','revision':'unspecified'},'compatible':'test,gpio','config_type':'gpio.bank','config_version':1,'config':{'pins':[7],'active_high':True,'pull_up':True,'debounce_us':0,'long_press_us':0,'click_min_us':0}},
 {'instance_id':15,'chip':{'vendor':'espressif','model':'esp32s3-wifi','revision':'unspecified'},'compatible':'espressif,esp32s3-wifi','config_type':'radio.integrated','config_version':1,'config':{'unit':0,'features':3}}]}
save('board.json',board)
m=json.loads((w/'drivers/twatch_wifi/manifest.json').read_text());m['file_name']='wifi.elf';save('wifi.json',m)
save('sleep.json',{'type':'driver','id':'test-sleep','version':'1.0.0','driver_abi':2,'architecture':'xtensa-esp32s3','file_name':'sleep.elf','requires':[{'capability':'hardware.device','api':1},{'capability':'platform.gpio','api':1}],'provides':[{'capability':'test.sleep','api':1}],'hardware_compatibility':[{'compatible':'test,gpio','revisions':['unspecified'],'config_type':'gpio.bank','config_version':1}]})
req=[{'capability':c,'api':1} for c in ['net.wifi','test.sleep','storage.key-value','alarm.service']]
for name,cap,api in [('rtc','rtc.clock',2),('haptic','haptic.effect',1),('audio','audio.output',1)]:
 save(name+'.json',{'type':'driver','id':name+'-test','version':'1.0.0','driver_abi':2,'architecture':'xtensa-esp32s3','file_name':name+'.elf','requires':[],'provides':[{'capability':cap,'api':api}]})
m=json.loads((u/'Services/alarm_service/points-manifest.json').read_text());m['file_name']='alarm.elf';save('alarm.json',m)
keys=[dict(key=k,namespace=ns,access=mode) for k,ns,mode in [('alarm_cfg',3,'read'),('timer_cfg',3,'read'),('alarm_occ',4,'read-write'),('timer_occ',4,'read-write'),('alert_mode',1,'read'),('points_cfg',5,'read'),('points_occ',4,'read-write')]]
for name,requires in [('default',req),('observer',[]),('consumer',[dict(capability=c,api=1) for c in ['net.wifi','storage.key-value']])]:save(name+'.json',{'type':'application','id':name,'version':'1.0.0','architecture':'xtensa-esp32s3','file_name':name+'.elf','entry':'app_main','requires':requires})
save('boot.json',{'board':'board.json','default_app':'default.elf','drivers':[{'manifest':'wifi.json','instance_id':15},{'manifest':'sleep.json','instance_id':7},*({'manifest':n+'.json'} for n in ['rtc','haptic','audio']),{'manifest':'alarm.json','key_value':keys}],'app_capabilities':[{'manifest':'default.json','grants':[dict(capability=c,api=1,instance_id=i) for c,i in [('net.wifi',15),('test.sleep',7),('storage.key-value',6),('alarm.service',0)]]},{'manifest':'observer.json','grants':[]},{'manifest':'consumer.json','grants':[dict(capability=c,api=1,instance_id=i) for c,i in [('net.wifi',15),('storage.key-value',6)]]}]})
for mode in ['normal','join-retry','cleanup-retry','cleanup-retained','live-return']:run([b/'test',b,mode])

# Now execute the actual shared Wi-Fi application/adapter as separately mapped
# modules against the same Runtime, native radio transport and alarm service.
for name,kind in [('display',1),('touch',2),('navigation',3)]:
 run(['cc',*san,'-std=c11','-Wall','-Wextra','-Werror','-fPIC','-fvisibility=hidden','-shared',*incs,'-DUI_KIND='+str(kind),here/'ui_provider.c','-o',b/(name+'.elf')])
run(['cc',*san,'-std=c11','-Wall','-Wextra','-Werror','-fPIC','-fvisibility=hidden','-shared',*incs,'-DPORTABLE_WIFI_SETTINGS_APP','-DPORTABLE_WIFI_INSTANCE=15','-DPORTABLE_WIFI_STORAGE_INSTANCE=6','-DPORTABLE_ALARM_CLIENT','-DPORTABLE_INPUT_NAVIGATION','-DPORTABLE_TOUCH_ROTATION=0','-DPORTABLE_FORCE_FULL_FRAMES','-DWIFI_RETURN_APP="springboard.elf"',s/'Apps/wifi_settings.c',s/'lib/PortableApps/src/adapter.c',here/'ui_catalog.c','-o',b/'default.elf'])
(b/'springboard.elf').write_bytes((b/'observer.elf').read_bytes())
for name,cap in [('display','display.output'),('touch','input.touch.raw'),('navigation','input.navigation')]:
 save(name+'.json',{'type':'driver','id':'test-'+name,'version':'1.0.0','driver_abi':2,'architecture':'xtensa-esp32s3','file_name':name+'.elf','requires':[],'provides':[{'capability':cap,'api':1}]})
manifest=json.loads((b/'observer.json').read_text());manifest.update(id='springboard',file_name='springboard.elf');save('springboard.json',manifest)
requires=['display.output','input.touch.raw','input.navigation','net.wifi','storage.key-value','alarm.service']
manifest=json.loads((b/'default.json').read_text());manifest['requires']=[dict(capability=c,api=1) for c in requires];save('default.json',manifest)
boot=json.loads((b/'boot.json').read_text());boot['drivers'] += [dict(manifest=n+'.json') for n in ['display','touch','navigation']]
boot['app_capabilities'][0]['grants']=[dict(capability=c,api=1,instance_id=15 if c=='net.wifi' else 6 if c=='storage.key-value' else 0) for c in requires]
boot['app_capabilities'][1]['manifest']='springboard.json';save('boot.json',boot)
run([b/'test',b,'real-ui'])
run([b/'test',b,'real-ui-display-failure'])
