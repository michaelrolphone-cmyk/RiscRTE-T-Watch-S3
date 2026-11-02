#!/usr/bin/env python3
"""Capacity-only native successor: full locked build; no app/store composition."""
import io
import re
import sys
import json
import shlex
import subprocess
import tempfile
from pathlib import Path
from elftools.elf.elffile import ELFFile
from package_alarm_sleep import make_archive

def require(ok, message):
    if not ok: raise ValueError(message)

def expanded(root, runtime, profile, cmake):
    with tempfile.TemporaryDirectory(prefix='home-profile-') as tmp:
        script=Path(tmp)/'profile.cmake'
        output=Path(tmp)/'profile.txt'
        script.write_text('set(RISC_RUNTIME_ROOT "'+str(runtime)+'")\ninclude("'+str(root/profile)+'")\n'
            'file(WRITE "'+str(output)+'" "definitions=${RISC_NATIVE_DEFINITIONS}\\ntarget=${RISC_NATIVE_TARGET}\\npartitions=${RISC_NATIVE_PARTITIONS}\\nsettings=${RISC_NATIVE_SETTINGS_HEADER}\\nextra=${RISC_NATIVE_EXTRA_SOURCES}\\nappdata=${RISC_NATIVE_APPDATA}\\niq=${RISC_NATIVE_IQ}\\nlink=${RISC_NATIVE_LINK_OPTIONS}\\n")\n')
        subprocess.run([str(cmake),'-P',str(script)],check=True)
        return dict(line.split('=',1) for line in output.read_text().splitlines())

def profile_delta(root,runtime,old,cmake):
    before=expanded(root,runtime,old,cmake)
    after=expanded(root,runtime,'profiles/shared-home-capacity.cmake',cmake)
    old_defs=before['definitions'].split(';')
    new_defs=after['definitions'].split(';')
    require(old_defs.count('RISC_PROVIDER_CAPACITY=40')==1,'Original provider capacity differs')
    require(new_defs.count('RISC_PROVIDER_CAPACITY=48')==1,'Successor provider capacity differs')
    require(sorted(x for x in old_defs if x!='RISC_PROVIDER_CAPACITY=40')==
            sorted(x for x in new_defs if x!='RISC_PROVIDER_CAPACITY=48'),'Non-capacity definition changed')
    require({k:v for k,v in before.items() if k!='definitions'}==
            {k:v for k,v in after.items() if k!='definitions'},'Non-definition profile selection changed')
    require('RISC_PLATFORM_CAPACITY=32' in new_defs,'Platform capacity changed')
    return before,after

def linked_capacity(raw):
    elf=ELFFile(io.BytesIO(raw))
    require(elf.has_dwarf_info(),'Linked type evidence absent')
    wanted={'Runtime':{'drivers_':48,'providerStorage_':48,'grants_':48,'platforms_':32},
            'GraphV2':{'nodes_':48},'Invocation':{'appGrants_':16}}
    found={}
    for cu in elf.get_dwarf_info().iter_CUs():
        name=cu.get_top_DIE().attributes.get('DW_AT_name')
        if not name or not name.value.decode().endswith('/src/bootstrap/Runtime.cpp'): continue
        for die in cu.iter_DIEs():
            name=die.attributes.get('DW_AT_name')
            if not name or name.value.decode() not in wanted: continue
            label=name.value.decode()
            if die.tag not in ('DW_TAG_class_type','DW_TAG_structure_type'): continue
            for member in die.iter_children():
                field=member.attributes.get('DW_AT_name')
                if member.tag!='DW_TAG_member' or not field: continue
                field=field.value.decode()
                if field not in wanted[label]: continue
                array=member.get_DIE_from_attribute('DW_AT_type')
                require(array.tag=='DW_TAG_array_type','Expected linked array')
                ranges=[x for x in array.iter_children() if x.tag=='DW_TAG_subrange_type']
                require(len(ranges)==1,'Expected one-dimensional linked array')
                attrs=ranges[0].attributes
                count=attrs['DW_AT_count'].value if 'DW_AT_count' in attrs else attrs['DW_AT_upper_bound'].value+1
                require(count==wanted[label][field],'Linked capacity differs: '+label+'.'+field)
                found[label+'.'+field]=count
    require(set(found)=={label+'.'+field for label,fields in wanted.items() for field in fields},'Incomplete linked capacity evidence')
    return found

def qualify(args,sources,proof,base,cmake):
    controlled,native=base.controlled,base.native
    p=json.loads((base.ROOT/'docs/shared-home-capacity/source-pins.json').read_bytes())
    lock=json.loads(args.lock.read_bytes())
    closure=controlled.validate_build_proof(proof,sources,args.native_build,args.compiler,lock)
    before,after=profile_delta(base.ROOT,sources['runtime'],p['profile'],cmake)
    commands=json.loads((args.native_build/'compile_commands.json').read_bytes())
    rows=[]
    for row in commands:
        source=Path(row['file']).resolve()
        if not source.is_relative_to(sources['runtime']/'src'): continue
        arguments=row.get('arguments') or shlex.split(row['command'])
        for flag in after['definitions'].split(';'):
            if not flag: continue
            prefix='-D'+flag.split('=',1)[0]+'='
            require([x for x in arguments if x.startswith(prefix)]==['-D'+flag],
                    'Actual compile selection differs: '+flag)
        rows.append(row)
    require(rows,'No Runtime compilation')
    import sys
    sys.path[:0]=[str(sources['runtime']/'scripts'),str(sources['image_helper']/'scripts')]
    contract=json.loads(native.CONTRACT.read_bytes())
    # The verifier's default remains the frozen original profile. This explicit
    # caller supplies the separately evaluated and delta-checked derivative.
    blobs,native_proof=native.verify_native(lock,sources,args.native_build,args.compiler,
        contract,args.baseline.read_bytes(),profile_text=after['definitions'])
    linked=linked_capacity(blobs['firmware_elf'])
    require(set(re.findall(rb'RISC_RUNTIME_VERSION:([^\x00]*)\x00',blobs['firmware_bin']))=={p['runtime_version'].encode()},'Runtime version marker differs')
    memory=args.native_build/'native-build-evidence/provider-capacity-layout'
    subprocess.run([sys.executable,str(sources['runtime']/'test/home_provider_capacity_layout.py'),'--build',str(args.native_build),'--runtime',str(sources['runtime']),'--output',str(memory)],check=True)
    measured=json.loads((memory/'memory.json').read_bytes())
    controlled.validate_build_proof(proof,sources,args.native_build,args.compiler,lock)
    native.verify_sources(lock,sources)
    report={'schema':1,'source_revision':lock['sources']['product']['revision'],
        'runtime_revision':p['runtime_revision'],'runtime_version':p['runtime_version'],'capacity_memory':measured,'profile_before':before,'profile_after':after,
        'compiled_runtime_rows':len(rows),'linked_capacity':linked,'native':native_proof,
        'build_closure_sha256':controlled.sha((args.native_build/'native-build-evidence/build-closure.json').read_bytes()),
        'scope':'Full native firmware dependency; final cumulative app/store graph admission is separate.',
        'hardware_tested':False,'device_accessed':False,'product_composed':False}
    assets={name:blobs[key] for name,key in [('firmware.bin','firmware_bin'),('firmware.elf','firmware_elf'),
        ('bootloader.bin','bootloader'),('partitions.bin','partitions')]}
    report['artifacts']={name:base.record(raw) for name,raw in assets.items()}
    assets['qualification.json']=base.encoded(report)
    assets['source-lock.json']=args.lock.read_bytes()
    args.output.mkdir(parents=True)
    for name,raw in assets.items(): (args.output/name).write_bytes(raw)
    archive={}
    for role,root in sources.items():
        if role=='sdk': continue
        archive[role+'-source.tar']=native.git(root,'archive','--format=tar','HEAD')
    archive['qualification.json']=assets['qualification.json']
    assets['sources.zip']=make_archive(archive)
    (args.output/'sources.zip').write_bytes(assets['sources.zip'])
    (args.output/'SHA256SUMS').write_text(''.join(controlled.sha(raw)+'  '+name+'\n' for name,raw in sorted(assets.items())))
    print(json.dumps(report,sort_keys=True),flush=True)
