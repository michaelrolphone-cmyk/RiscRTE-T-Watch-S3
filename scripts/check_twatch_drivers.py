#!/usr/bin/env python3
"""Validate schema, compatible matching, physical ownership, DAG and packages."""
import copy,hashlib,json,re,zipfile
from pathlib import Path
import jsonschema
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
def check_board(b,manifests):
    schema=read(ROOT/'docs/twatch-board-v1.schema.json')
    errors=list(jsonschema.Draft202012Validator(schema).iter_errors(b))
    assert not errors,[(list(e.path),e.message[:120]) for e in errors]
    buses={x['instance_id']:x for x in b['buses']};devices={x['instance_id']:x for x in b['devices']}
    assert len(buses)==len(b['buses']) and len(devices)==len(b['devices']) and not set(buses)&set(devices)
    pins={};addresses=set();controllers=set();graph={}
    def own(pin,owner):
        if pin==-1:return
        assert pin not in pins,(pin,owner,pins.get(pin));pins[pin]=owner
    for bus in buses.values():
        namespace=bus.get('controller_namespace');assert namespace in ('esp32.peripheral','riscrte.logical')
        physical=bus.get('physical_controller',bus['controller']);assert namespace!='esp32.peripheral' or physical==bus['controller']
        assert bus['kind']!='spi' or physical in (2,3)
        assert bus['kind']!='i2c' or physical in (0,1)
        assert (bus['kind'],physical) not in controllers;controllers.add((bus['kind'],physical))
        assert bus['mode']==0
        fields=('sda','scl') if bus['kind']=='i2c' else ('sclk','mosi','miso')
        for k in fields:
            pin=bus['pins'][k];assert pin>=0 or k=='miso';own(pin,'bus'+str(bus['instance_id']))
        for k in set(bus['pins'])-set(fields):assert bus['pins'][k]==-1
    for d in devices.values():
        candidates=[m for m in manifests if any(h['compatible']==d['compatible'] and d['chip']['revision'] in h['revisions'] and h['config_type']==d['config_type'] and h['config_version']==d['config_version'] for h in m.get('hardware_compatibility',[]))]
        assert len(candidates)==1,(d['compatible'],len(candidates));m=candidates[0];c=d['config'];base=c.get('device',c)
        deps=d.get('bindings',{});graph[d['instance_id']]=set(deps.values());assert set(deps.values())<=set(devices)
        for cap,target in deps.items():
            td=devices[target];tm=next(x for x in manifests if any(h['compatible']==td['compatible'] and h['config_type']==td['config_type'] for h in x.get('hardware_compatibility',[])))
            assert any(p['capability']==cap for p in tm['provides']),(cap,target)
        if 'bus_instance_id' in base:
            bid=base['bus_instance_id'];assert bid in buses
            if 'address'in base:
                assert buses[bid]['kind']=='i2c';key=(bid,base['address']);assert key not in addresses;addresses.add(key)
                assert 'i2c.bus'in deps and devices[deps['i2c.bus']]['config']['bus_instance_id']==bid
        if d['config_type']=='power.axp2101':
            assert c['charge_ma']==100 and len({x['id'] for x in c['rails']})==len(c['rails'])
            for r in c['rails']:assert r['millivolts']%100==0
        for key in ('cs','dc','reset','backlight','busy','irq','bclk','ws','data'):
            if key in base:own(base[key],d['instance_id'])
        for pin in base.get('pins',[]):own(pin,d['instance_id'])
        if d['config_type']=='radio.lora':
            assert c['minimum_hz']<=c['maximum_hz']
            assert buses[c['bus_instance_id']]['frequency_hz']<=10000000
    done=set()
    def visit(i,active):
        assert i not in active,'dependency cycle'
        if i in done:return
        for j in graph[i]:visit(j,active|{i})
        done.add(i)
    for i in graph:visit(i,set())
    return len(pins)
def main():
    manifests=[read(p) for p in sorted((ROOT/'drivers').glob('*/manifest.json'))]
    assert len({m['id'] for m in manifests})==len(manifests)
    for m in manifests:
        assert m['driver_abi']==2 and m['architecture']=='xtensa-esp32s3' and re.fullmatch(r'\d+\.\d+\.\d+',m['version']) and m['physical_verification']=='pending'
        assert len({x['capability'] for x in m['requires']})==len(m['requires'])
    for name,source in read(ROOT/'sdk/SOURCES.json').items():assert hashlib.sha256((ROOT/'sdk/driver'/name).read_bytes()).hexdigest()==source['sha256'],name
    profiles=read(ROOT/'board.json');assert profiles['default'] is None
    for p in profiles['profiles']:check_board(read(ROOT/p),manifests)
    original=read(ROOT/profiles['profiles'][0]);bad=[]
    b=copy.deepcopy(original);b['devices'][0]['compatible']='unknown,chip';bad.append(b)
    b=copy.deepcopy(original);b['devices'][5]['config']['irq']=21;bad.append(b)
    b=copy.deepcopy(original);b['devices'][7]['config']['address']=25;bad.append(b)
    b=copy.deepcopy(original);b['devices'][5]['bindings']['i2c.bus']=2;bad.append(b)
    b=copy.deepcopy(original);b['devices'][4]['config_version']=2;bad.append(b)
    b=copy.deepcopy(original);b['devices'][3]['config']['charge_ma']=125;bad.append(b)
    b=copy.deepcopy(original);b['devices'][1]['bindings']={'gpio.bank':1};b['devices'][0]['bindings']={'i2c.bus':2};bad.append(b)
    b=copy.deepcopy(original);b['devices'][8]['config']['extra']=0;bad.append(b)
    for i,b in enumerate(bad):
        try:check_board(b,manifests)
        except AssertionError:continue
        raise AssertionError(f'invalid mapping {i} accepted')
    print(len(profiles['profiles']),'board variants;',len(bad),'invalid mappings rejected;',len(manifests),'driver manifests')
    catalog=ROOT/'dist/catalog.json'
    if catalog.exists():
        rows=read(catalog)['packages'];assert len(rows)==len(manifests)
        for row in rows:
            path=ROOT/'dist'/row['archive'];blob=path.read_bytes();assert len(blob)==row['size_bytes'] and hashlib.sha256(blob).hexdigest()==row['sha256']
            with zipfile.ZipFile(path) as z:
                m=json.loads(z.read('.package.json'));source=next(x for x in manifests if x['id']==row['id']);assert m['id']==source['id'] and m['version']==source['version']==row['version']
                assert m.get('hardware_compatibility',[])==source.get('hardware_compatibility',[])
                assert m['provides']==source['provides'] and m['requires']==[dict(capability=x['capability'],min_api=x['api']) for x in source['requires']]
                for entry in m['entries']:
                    b=z.read(entry['name']);assert len(b)==entry['size_bytes'] and hashlib.sha256(b).hexdigest()==entry['sha256']
                cap=source['provides'][0];assert z.read('provider-abi.v1')==f"os-cpu-abi=1\nprovides={cap['capability']}\napi={cap['api']}\n".encode()
        print(len(rows),'package/catalog/hash checks passed')
if __name__=='__main__':main()
