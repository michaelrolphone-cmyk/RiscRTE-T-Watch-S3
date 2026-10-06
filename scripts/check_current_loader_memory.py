#!/usr/bin/env python3
"""Execute current target ELF allocation, section and relocation proofs.

Offline fault injection only. No execution of Xtensa code, devices or firmware
writes. Requires the exact Runtime, Utilities fixtures and current Watch package.
"""
import argparse,hashlib,json,os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def extract(text,signature):
 start=text.index(signature);opening=text.index('{',start);depth=0
 for pos in range(opening,len(text)):
  if text[pos]=='{':depth+=1
  elif text[pos]=='}':
   depth-=1
   if not depth:return text[start:pos+1]
 raise ValueError('Incomplete loader function')
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path,required=True);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--store',type=Path);g.add_argument('--image',type=Path);g.add_argument('--bin',type=Path);p.add_argument('--utilities',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
runtime=args.runtime.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
pins=json.loads((ROOT/'apps/current-apps-sources.json').read_text())['sources']
for name,path in [('runtime',runtime),('utilities',args.utilities)]:
 if subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip()!=pins[name]['commit']:raise ValueError('Wrong pinned source: '+name)
 if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=path,text=True).strip():raise ValueError('Dirty pinned source: '+name)
image_sha=None
if args.image or args.bin:
 from read_only_spiffs import read_image
 from current_flash_layout import validate
 deployment=json.loads((ROOT/'apps/current-runtime-requirements.json').read_text())['deployment'];validate(deployment,True)
 data=(args.image or args.bin).read_bytes();image_sha=hashlib.sha256(data).hexdigest()
 if args.bin:
  if len(data)!=deployment['flash_bytes']:raise ValueError('Wrong full BIN size')
  partition=deployment['partitions']['bootfs0'];data=data[partition['offset']:partition['offset']+partition['size']]
 files=read_image(data,deployment['partitions']['bootfs0']['size'])
 temporary=tempfile.TemporaryDirectory(prefix='current-loader-store-');args.store=Path(temporary.name)
 for name,content in files.items():
  path=args.store/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)

adapter=runtime/'lib/elf_loader/src/esp_elf_adapter.c';loader=runtime/'lib/elf_loader/src/esp_elf.c';config=(runtime/'platformio.ini').read_text()
for flag in ['CONFIG_ELF_LOADER_LOAD_PSRAM=1','CONFIG_ELF_LOADER_BUS_ADDRESS_MIRROR=1']:
 if flag not in config:raise ValueError('Deployment lacks required no-fallback PSRAM loader config: '+flag)
allocation=extract(adapter.read_text(),'void *esp_elf_malloc(');sections=extract(loader.read_text(),'static int esp_elf_load_section(')
(out/'sdkconfig.h').write_text('#define CONFIG_ELF_LOADER_BUS_ADDRESS_MIRROR 1\n#define CONFIG_ELF_LOADER_LOAD_PSRAM 1\n')
source=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
#include "private/elf_types.h"
#include "private/esp_elf_data_layout.h"
#define MALLOC_CAP_SPIRAM 4u
#define MALLOC_CAP_8BIT 8u
#define ESP_IDF_VERSION 40407
#define ESP_IDF_VERSION_VAL(a,b,c) ((a)*10000+(b)*100+(c))
#define ESP_LOGD(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define stype(s,t) ((s)->type==(t))
#define sflags(s,f) (((s)->flags&(f))==(f))
static unsigned calls,fail_at,live;
static uint32_t requested[3];
static void* heap_caps_malloc(uint32_t n,uint32_t caps){
 assert(caps==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));assert(calls<3);requested[calls++]=n;
 if(calls==fail_at)return NULL;void*p=malloc(n);assert(p);++live;return p;
}
static void esp_elf_free(void*p){if(p){assert(live);--live;free(p);}}
'''+allocation+'\n'+sections+r'''
int main(int argc,char**argv){
 assert(argc==2);FILE*f=fopen(argv[1],"rb");assert(f);assert(!fseek(f,0,SEEK_END));long n=ftell(f);assert(n>0);rewind(f);uint8_t*bytes=malloc((size_t)n);assert(bytes);assert(fread(bytes,1,(size_t)n,f)==(size_t)n);fclose(f);
 for(unsigned scenario=1;scenario<=3;++scenario){
  calls=live=0;fail_at=scenario<3?scenario:0;esp_elf_t elf={0};int result=esp_elf_load_section(&elf,bytes);
  if(fail_at){assert(result==-ENOMEM);assert(calls==fail_at);assert(!live&&!elf.entry&&!elf.ptext&&!elf.pdata);}
  else {assert(result==0&&calls==2&&live==2);assert(requested[0]+requested[1]<=1024u*1024u);printf("{\"text\":%u,\"data\":%u,\"bss\":%zu}\n",requested[0],requested[1],elf.sec[ELF_SEC_BSS].size);esp_elf_free(elf.pdata);esp_elf_free(elf.ptext);assert(!live);}
 }
 free(bytes);return 0;
}
'''
(out/'loader.c').write_text(source);binary=out/'loader'
subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-Wno-unused-parameter','-Wno-pointer-to-int-cast','-Wno-int-to-pointer-cast','-I'+str(out),'-I'+str(runtime/'lib/elf_loader/include'),str(out/'loader.c'),'-o',str(binary)],check=True)
files=sorted(args.store.rglob('*.elf'))
if len(files)!=35 or len(list(args.store.glob('*.elf')))!=19:raise ValueError('Expected 19 app ELFs and 16 unique provider ELFs for 17 selected instances')
measurements={}
for path in files:
 result=subprocess.run([str(binary),str(path)],check=True,capture_output=True,text=True)
 value=json.loads(result.stdout);value['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();value['file_bytes']=path.stat().st_size
 measurements[str(path.relative_to(args.store))]=value
# The pinned consumer fixture executes the entire real Xtensa relocation path,
# checks all mapped bytes independently, and guards eight allocator residues.
fixture=args.utilities/'test/alarm_target_loader.c';stubs=args.utilities/'test/alarm-loader-stubs'
relocator=out/'relocator'
subprocess.run([os.environ.get('CC','cc'),'-std=gnu11','-O1','-g','-Wno-pointer-to-int-cast',
 '-I'+str(stubs),'-I'+str(runtime/'lib/elf_loader/include'),str(fixture),
 *[str(runtime/'lib/elf_loader/src'/name) for name in ('esp_elf.c','arch/esp_elf_xtensa.c','esp_elf_validate.c')],'-o',str(relocator)],check=True)
proof=subprocess.run([str(relocator),*map(str,files)],check=True,capture_output=True,text=True)
(out/'relocations.log').write_text(proof.stdout)
boot=json.loads((args.store/'boot.json').read_text());providers=0
if len(boot['drivers'])!=17:raise ValueError('Expected 17 selected provider instances')
for item in boot['drivers']:
 manifest_path=Path(item['manifest']);manifest=json.loads((args.store/manifest_path).read_text())
 value=measurements[(manifest_path.parent/manifest['file_name']).as_posix()]
 providers+=value['text']+value['data']
apps={n:v for n,v in measurements.items() if '/' not in n}
peak=max(v['text']+v['data']+v['file_bytes'] for v in apps.values())
# Conservative complete-provider residency, largest app and raw ELF scratch,
# plus two RGB565 frames. Physical free heap and native radio/audio allocations
# remain separate hardware measurements; this is not a free-heap prediction.
subtotal=providers+peak+2*240*240*2
if subtotal>4*1024*1024:raise ValueError('Cohort loader subtotal exceeds 4 MiB regression budget')
record={'scope':'offline production loader/relocation execution; no target instructions or physical heap qualification',
 'runtime_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=runtime,text=True).strip(),
 'source_sha256':{str(p.relative_to(runtime)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [adapter,loader,runtime/'platformio.ini']},
 'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(), 'files':measurements, 'input_image_sha256':image_sha,
 'all_provider_resident_bytes':providers,'largest_app_and_input_bytes':peak,'two_frame_bytes':230400,
 'conservative_loader_frame_subtotal_bytes':subtotal,'software_budget_bytes':4*1024*1024,
 'checks':['exact PSRAM flags; no internal fallback','text/data OOM before entry with cleanup',
 'each module allocation below 1 MiB','eight allocator residues; exact mapped bytes and relocation targets; redzones intact'],
 'physical_heap_and_current':'pending'}
(out/'evidence.json').write_text(json.dumps(record,indent=2)+'\n')
print('All 35 target ELFs: allocation failures, PSRAM-only mapping, relocation/alignment and software memory budget passed:',subtotal)
