#!/usr/bin/env python3
"""Replay selected Files 1.5.34 target profiles with only optional modal policy.

Builds component ELFs, never native firmware or full images. Public qualification
requires an exact clean public System commit selected in selection.json.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from compact_current_elf import compact
from build_lora_policy import compile_exact, git, require

ROOT = Path(__file__).resolve().parents[1]
SELECTION_PATH = ROOT / 'docs/files-input-policy/selection.json'
VERSION = '1.5.35'
FEATURE_ADDITIONS = ['-DPORTABLE_TEXT_INPUT_POLICY']
PREDECESSOR_SYSTEM = 'e3fd26c2257cef91c8f6a7b98065b52f1db7a54d'
SOURCE_BASE = 'fd4b1e52fe2a49c3c4c22f9ccd4c98a91f88afa0'
OLD_SYSTEM = '/workspace/shared/files-shared-input-system-published-20261012'
PREDECESSORS = Path('/workspace/shared/files-shared-input-published-components-20261012')
CC = '/workspace/scratch/c744abbbbd60/watch-build-tools/platformio-core/packages/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-gcc'
PINNED = {
 'watch': {'manifest': '02aaa7bb7d8cdf24a534acda8993aa2b2156182bdc6acf626c6820e6758f8d64', 'record': '36803e7680a09e24524dd361ccb92371625afe5b2251ace29fcd944c05166cc4', 'elf': '2265a75e0f1226f9b885207dfd176d335593703aa5721f1581dee08dfa87c583'},
 'x4': {'manifest': '3afc4c6f39e48dcc6fbab0baf85ed48cd74326dadf519e14cca731ac5bf57214', 'record': 'd29577decd045ed87ac123b973775c9cb7d8bfa9d9e3e6e1e3ff276c0eb64527', 'elf': 'c3b8afbe8e80e74ffc191e29e1b72cf392777993d4e5fe77aa317ff5670ff01e'},
}

def sha(path):
 return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_selection():
 return json.loads(SELECTION_PATH.read_text())

SELECTION = load_selection()

def source_guard(system, commit, provisional):
 require(git(system, 'rev-parse', 'HEAD') == commit, 'Wrong System source commit')
 if not provisional:
  selection = load_selection()
  require(selection['finalized'] and selection['source_publication'] == 'public-exact-commit' and
          commit == selection['sources']['system-apps'], 'Public source selection is not finalized')
  require(not git(system, 'status', '--porcelain', '--untracked-files=no'), 'Dirty System source')


def selected_predecessor(device):
 folder = PREDECESSORS / (device + '-files')
 record_path = folder / 'file_browser-build-record.json'
 require(sha(record_path) == PINNED[device]['record'], 'Selected predecessor receipt changed')
 record = json.loads(record_path.read_text())
 require(record['version'] == '1.5.34' and record['sha256'] == PINNED[device]['elf'] and
         sha(folder / 'file_browser.elf') == record['sha256'], 'Selected predecessor ELF changed')
 require(sha(folder / 'file_browser.json') == PINNED[device]['manifest'], 'Selected predecessor manifest changed')
 manifest = json.loads((folder / 'file_browser.json').read_text())
 require(manifest['version'] == '1.5.34' and manifest['requires'].count({'capability':'ui.text-input','api':1}) == 1,
         'Selected predecessor manifest authority changed')
 return folder, record, manifest


def stage_inputs(device, system, out, predecessor, prior):
 """Copy generated target inputs and original pinned SDK overrides only."""
 copied = {}
 selected_inputs = load_selection()['predecessor_input_sha256'][device]
 names = ['sharing-objects', 'empty_catalog.c', 'exports.map', 'watch-alarm-profile.h'] if device == 'watch' else [
          'sharing-objects', 'catalog.c', 'file_browser.map', 'native-time-sdk']
 for name in names:
  source = predecessor / name
  targets = list(source.rglob('*')) if source.is_dir() else [source]
  for path in targets:
   if not path.is_file(): continue
   relative = path.relative_to(predecessor)
   require(sha(path) == selected_inputs.get(relative.as_posix()), 'Changed selected generated input: '+str(relative))
   destination = out / relative
   destination.parent.mkdir(parents=True, exist_ok=True)
   shutil.copyfile(path, destination)
   copied[relative.as_posix()] = {'predecessor_sha256': sha(path), 'selected_sha256': sha(destination), 'operation': 'unchanged selected generated input'}
 if device == 'x4':
  pinned_sdk = set(prior['native_time_sdk']['sha256']) | set(prior['tagged_alarm_sdk']['sha256']) | set(prior['resident_shell']['sdk_sha256'])
  # Native and resident API headers remain byte-identical to selected SDK.
  # Portable client headers track the selected System source, including policy.
  for source in (system / 'lib/PortableApps/include').iterdir():
   if not source.is_file() or source.name in pinned_sdk: continue
   destination = out / 'native-time-sdk/include' / source.name
   shutil.copyfile(source, destination)
   relative = destination.relative_to(out).as_posix()
   copied[relative] = dict(predecessor_sha256=copied.get(relative, {}).get('predecessor_sha256'),
                          selected_sha256=sha(destination), operation='selected System portable header',
                          source=str(source))
 return copied


def command_for(device, system, out, predecessor, prior, policy=True):
 def relocate(value):
  return value.replace(OLD_SYSTEM, str(system)).replace(str(predecessor), str(out))
 inherited = [relocate(value) for value in prior['defines']]
 require(not any(value in inherited for value in FEATURE_ADDITIONS), 'Policy already enabled in predecessor')
 if device == 'watch':
  command = [relocate(value) for value in prior['command']]
 else:
  sources = [system/'Apps/file_browser.c', system/'lib/PortableApps/src/adapter.c', out/'catalog.c']
  sources += [system/'lib/PortableApps/src'/name for name in ('PortableNativeTimeSource.c','PortableRealtimeClient.c',
              'PortableTimeZone.c','PortableTimeZoneCatalog.c','PortableTimeZonePreference.c','PortableNetworkSession.c')]
  sources += [out/'sharing-objects'/(name+'.o') for name in ('WebDavCore','WebDavVolume','WebDavProperties',
              'WebDavSession','WebDavDigest','WebDavSharing','PortableFileSharing','WebDavClient','WebDavRemoteVolume','PortablePeerFiles','sha2')]
  sources += [system/'lib/PortableApps/src/PortableFileSetup.c']
  command = [CC,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden',
             '-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-Wl,--no-relax','-Wl,--hash-style=sysv',
             '-Wl,--version-script='+str(out/'file_browser.map'),'-Wall','-Wextra','-Werror',*inherited,
             '-I'+str(out/'native-time-sdk/include'),'-I'+str(system/'lib/NativeApps/include'),*map(str,sources),
             '-lgcc','-o',str(out/'file_browser.elf')]
 command[0] = os.environ.get('NATIVE_APP_CC', command[0])
 before = list(command)
 if policy: command[command.index('-o'):command.index('-o')] = FEATURE_ADDITIONS
 require([v for v in command if v not in FEATURE_ADDITIONS] == before, 'Inherited target options changed')
 return command, inherited


def closure(command, flags):
 dependencies = {}
 includes = [value for value in command if value.startswith('-I')]
 for source in [Path(v) for v in command if v.endswith('.c')]:
  output = subprocess.check_output([command[0],'-std=c11','-Os','-fPIC','-ffreestanding','-fno-builtin','-MM',
                                    *flags,*includes,str(source)],text=True)
  for token in shlex.split(output.replace('\\\n',' ').split(':',1)[1]):
   path = Path(token).resolve()
   require(path.is_file() and not {'test','tests','fixtures'} & set(path.parts), 'Invalid target input: '+token)
   dependencies[str(path)] = {'sha256': sha(path), 'bytes': path.stat().st_size}
 for token in command:
  if token.endswith('.o'):
   dependencies[str(Path(token).resolve())] = {'sha256': sha(token), 'bytes': Path(token).stat().st_size}
 return dependencies


def verify_fonts(device, system, prior, dependencies):
 found = {}
 for name, digest in prior['source_sha256'].items():
  if not any('/'+group+'/' in '/'+name for group in ('fonts','settings_fonts','paper_fonts','quick_fonts','home_fonts')): continue
  relative = name.removeprefix(OLD_SYSTEM+'/')
  path = system/relative
  require(path.is_file() and sha(path) == digest, 'Original font changed: '+relative)
  found[relative] = digest
 require(found, 'No inherited font provenance')
 return found


def build(args):
 device, system, out = args.device, args.system.resolve(), args.output.resolve()
 source_guard(system,args.system_commit,args.provisional)
 recipe = git(ROOT,'rev-parse','HEAD')
 if not args.provisional: require(not git(ROOT,'status','--porcelain','--untracked-files=no'),'Dirty public recipe')
 require(not out.exists(), 'Use a fresh output directory')
 predecessor, prior, manifest = selected_predecessor(device)
 out.mkdir(parents=True)
 generated = stage_inputs(device,system,out,predecessor,prior)
 command,inherited = command_for(device,system,out,predecessor,prior,not args.flag_off)
 flags = inherited + ([] if args.flag_off else FEATURE_ADDITIONS)
 compiler = subprocess.check_output([command[0],'--version'],text=True).splitlines()[0]
 require('8.4.0' in compiler and '2021r2-patch5' in compiler,'Wrong target compiler')
 dependencies = closure(command, flags)
 fonts = verify_fonts(device,system,prior,dependencies)
 if not args.flag_off:
  for name in ('PortableTextInputPolicy.h','PortableTextInputCheckpointClient.h'):
   require(any(key.endswith('/'+name) for key in dependencies), 'Missing modal dependency: '+name)
 elf = out/'file_browser.elf'
 attempts = compile_exact(command,elf,out/'debug/linker-attempts')
 validator = out/'validate-elf'
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(system/'test/native_apps/stubs'),
                 '-I'+str(system/'lib/elf_loader/include'),str(system/'lib/elf_loader/src/esp_elf_validate.c'),
                 str(system/'test/native_apps/validate_test.c'),'-o',str(validator)],check=True)
 subprocess.run([str(validator),str(elf)],check=True)
 (out/'debug').mkdir(exist_ok=True)
 if device == 'watch':
  compaction = compact(elf,command[0],debug_path=out/'debug/file_browser.elf')
 else:
  shutil.copyfile(elf,out/'debug/file_browser.elf')
  compaction = {'profile':'unchanged-x4-uncompacted','before_bytes':elf.stat().st_size,'after_bytes':elf.stat().st_size}
 subprocess.run([str(validator),str(elf)],check=True)
 nm = subprocess.check_output([command[0].removesuffix('gcc')+'nm','-D',str(elf)],text=True)
 imports = {line.split()[-1] for line in nm.splitlines() if ' U ' in ' '+line}
 exports = {line.split()[-1] for line in nm.splitlines() if len(line.split())>=3 and line.split()[-2] in ('T','D','B','R')}
 require(imports == set(prior['imports']) and exports == set(prior['exports']), 'Inherited Files ABI changed')
 for name,row in dependencies.items(): require(sha(name)==row['sha256'],'Source changed during build: '+name)
 source_guard(system,args.system_commit,args.provisional)
 require(git(ROOT,'rev-parse','HEAD') == recipe,'Recipe changed during target build')
 if not args.provisional: require(not git(ROOT,'status','--porcelain','--untracked-files=no'),'Public recipe changed during target build')
 manifest['version'] = '1.5.34' if args.flag_off else VERSION
 (out/'file_browser.json').write_text(json.dumps(manifest,separators=(',',':'))+'\n')
 record = dict(schema='files.modal-policy.component.v1',device=device,version=manifest['version'],sha256=sha(elf),
  bytes=elf.stat().st_size,manifest_sha256=sha(out/'file_browser.json'),sources={'system-apps':args.system_commit},
  source_roots={'system-apps':str(system),'generated':str(out)},source_publication='local-provisional' if args.provisional else 'public-exact-commit',
  recipe_commit=recipe,recipe_sha256=sha(__file__),compiler=compiler,command=command,defines=flags,
  inherited_defines=inherited,feature_additions=[] if args.flag_off else FEATURE_ADDITIONS,target_dependencies=dependencies,
  generated_provenance=generated,original_font_sha256=fonts,original_fonts_retained=True,baseline_features_preserved=True,
  predecessor_record_sha256=PINNED[device]['record'],predecessor_elf_sha256=PINNED[device]['elf'],
  required_grants=prior['required_grants'],imports=sorted(imports),exports=sorted(exports),compaction=compaction,
  linker_attempts=attempts,shared_text_input=True,modal_policy=not args.flag_off,native_changed=False,hardware_verified=False,
  target_instructions_executed=False,flag_off_selected_predecessor_equal=sha(elf)==PINNED[device]['elf'] if args.flag_off else None)
 (out/'file_browser-build-record.json').write_text(json.dumps(record,indent=2)+'\n')
 print(device,manifest['version'],record['bytes'],record['sha256'])
 return record


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--device',choices=['watch','x4'],required=True)
 p.add_argument('--system',type=Path,required=True)
 p.add_argument('--system-commit',required=True)
 p.add_argument('--output',type=Path,required=True)
 p.add_argument('--provisional',action='store_true',help='Local evidence only; never public qualification')
 p.add_argument('--flag-off',action='store_true')
 build(p.parse_args())
if __name__=='__main__': main()
