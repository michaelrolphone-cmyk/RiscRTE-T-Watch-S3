#!/usr/bin/env python3
"""Production C code against bounded resource/transport mocks, native UBSan."""
import json,os,subprocess
from pathlib import Path
from generate_board import generate
ROOT=Path(__file__).resolve().parents[1]
TYPES={'controller.gpio':'tw_hw_gpio_controller_v1','controller.i2c':'tw_hw_i2c_controller_v1','power.axp2101':'tw_hw_axp2101_v1','display.spi':'risc_hw_spi_display_v1','touch.i2c':'risc_hw_i2c_touch_v1','peripheral.i2c':'tw_hw_i2c_device_v1','gpio.bank':'risc_hw_gpio_bank_v1','radio.lora':'tw_hw_lora_v1','audio.i2s':'tw_hw_audio_v1','radio.integrated':'risc_hw_radio_v1'}
def initializer(v):
    if isinstance(v,dict):return '{'+','.join('.'+k+'='+initializer(x) for k,x in v.items())+'}'
    if isinstance(v,list):return '{'+','.join(initializer(x) for x in v)+'}'
    if isinstance(v,bool):return '1' if v else '0'
    return str(v)
def config(entry,buses,alternate):
    def expand(c):
        c=dict(c)
        if 'bus_instance_id'in c:
            bus=dict(buses[c.pop('bus_instance_id')]);bus['kind']=1 if bus['kind']=='spi' else 2;bus.update(bus.pop('pins'));bus['struct_size']='sizeof(risc_hw_bus_v1)';c['bus']=bus
        if 'device'in c:c['device']=expand(c['device'])
        return c
    c=expand(entry['config']);typ=TYPES[entry['config_type']]
    if entry['config_type']=='gpio.bank':c['count']=len(c['pins'])
    if entry['config_type']=='display.spi':c['power_count']=len(c['power_pins'])
    if entry['config_type']=='power.axp2101':c['rail_count']=len(c['rails'])
    c['struct_size']='sizeof('+typ+')' if 'device'not in c else None
    if 'device'in c:del c['struct_size'];c['device']['struct_size']='sizeof('+typ+')'
    if alternate:
        fields={'sclk','mosi','miso','sda','scl','cs','dc','reset','backlight','busy','irq','bclk','ws','data'}
        def shift(x):
            for k,v in x.items():
                if isinstance(v,dict):shift(v)
                elif k in fields and isinstance(v,int) and v>=0:x[k]=(v+19)%49
                elif k=='pins':x[k]=[(p+19)%49 for p in v]
        shift(c)
        if entry['config_type']=='display.spi':c['bus']['frequency_hz']=2000000
    return typ,c
def main():
    gen=generate();cc=os.environ.get('CC','clang');total=0
    for alternate in (False,True):
        board=json.loads((ROOT/'hardware'/('sx1280-2400-bma456h.json' if alternate else 'sx1262-915-bma423.json')).read_text());buses={b['instance_id']:b for b in board['buses']}
        for kind,entry in enumerate(board['devices'],1):
            mp=next(p for p in (ROOT/'drivers').glob('*/manifest.json') if any(h['compatible']==entry['compatible'] and h['config_type']==entry['config_type'] for h in json.loads(p.read_text()).get('hardware_compatibility',[])));entry['driver']=json.loads(mp.read_text())['id'];src=next(mp.parent.glob('*.c'));typ,c=config(entry,buses,alternate)
            config_header=f'static {typ} m_config={initializer(c)};\nstatic risc_hardware_device_v1 m_device={{1,sizeof(m_device),{entry["instance_id"]},"{entry["compatible"]}","unspecified","{entry["config_type"]}",1,sizeof(m_config),&m_config}};\n'
            (gen/'fixture_config.h').write_text(config_header)
            out=ROOT/'dist'/f'test-{entry["driver"]}-{int(alternate)}'
            args=[cc,'-std=c11','-g','-fsanitize=undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'sdk/driver'),'-I'+str(ROOT/'include'),'-I'+str(gen),'-I'+str(ROOT),f'-DTEST_KIND={kind}',f'-DDRIVER_SOURCE="{src}"',str(ROOT/'tests/driver_test.c'),'-o',str(out)]
            subprocess.run(args,check=True);subprocess.run([str(out)],check=True);total+=1
    # Catalog selection has no hardware dependencies.
    out=ROOT/'dist/test-board'
    subprocess.run([cc,'-std=c11','-fsanitize=undefined','-I'+str(ROOT/'sdk/driver'),'-I'+str(ROOT/'include'),'-I'+str(gen),str(ROOT/'tests/board_test.c'),'-o',str(out)],check=True);subprocess.run([str(out)],check=True);total+=1
    common=[cc,'-std=c11','-fsanitize=undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'sdk/driver'),'-I'+str(ROOT/'include')]
    objects=[]
    for name in ['first','second']:
        obj=ROOT/'dist'/f'multi-{name}.o';objects.append(str(obj))
        subprocess.run(common+['-Dt5_driver_get='+name+'_get','-c',str(ROOT/'drivers/twatch_i2c/i2c_main.c'),'-o',str(obj)],check=True)
    executable=ROOT/'dist/test-multi-instance'
    subprocess.run(common+[str(ROOT/'tests/multi_instance.c'),*objects,'-o',str(executable)],check=True)
    subprocess.run([str(executable)],check=True);total+=1
    print(total,'production contract fixtures passed (UBSan)')
if __name__=='__main__':main()
