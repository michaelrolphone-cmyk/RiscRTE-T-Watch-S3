#!/usr/bin/env python3
"""Build a later Watch Points 0.6.14 component; sealed delivery inputs stay read-only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from compact_current_elf import compact
from pack_points_elf_metadata import pack as pack_metadata
from build_lora_policy import compile_exact, git, require, relocate

ROOT = Path(__file__).resolve().parents[1]
SELECTION_PATH = ROOT / 'docs/points-input-policy/selection.json'
VERSION = '0.6.14'
FEATURE_ADDITIONS = ['-DPORTABLE_TEXT_INPUT_POLICY']
PREDECESSOR = Path('/workspace/shared/watch-points-components-20261012')
GENERATED = Path('/workspace/shared/watch-points-target-published-20261012')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_selection():
    return json.loads(SELECTION_PATH.read_text())

SELECTION = load_selection()
PINNED = SELECTION['predecessor']

def source_guard(roots, pins, provisional):
    selection = load_selection()
    if not provisional:
        require(selection['finalized'] and selection['source_publication'] == 'public-exact-commit',
                'Public Points source selection is not finalized')
        require(pins == selection['sources'], 'Public Points source selection differs')
    for owner, pin in pins.items():
        require(git(roots[owner], 'rev-parse', 'HEAD') == pin, 'Wrong source commit: ' + owner)
        if owner != 'productivity' or not provisional:
            require(not git(roots[owner], 'status', '--porcelain', '--untracked-files=no'), 'Dirty source: ' + owner)

def selected_predecessor():
    require(sha(PREDECESSOR/'evidence/points-build.json') == PINNED['record_sha256'], 'Changed selected predecessor receipt')
    record = json.loads((PREDECESSOR/'evidence/points-build.json').read_text())
    require(record['version'] == '0.6.13' and record['sha256'] == PINNED['elf_sha256'] and
            sha(PREDECESSOR/'store/points_in_time.elf') == PINNED['elf_sha256'], 'Changed selected predecessor ELF')
    require(sha(PREDECESSOR/'store/points_in_time.json') == PINNED['manifest_sha256'], 'Changed selected predecessor manifest')
    manifest = json.loads((PREDECESSOR/'store/points_in_time.json').read_text())
    require(manifest['version'] == '0.6.13' and manifest['requires'].count({'capability':'ui.text-input','api':1}) == 1,
            'Wrong selected predecessor authority')
    return record, manifest

def command_for(prior, roots, policy=True):
    mapped = lambda value: relocate(value, prior['source_roots'], roots)
    inherited = [mapped(value) for value in prior['defines']]
    require(not any(value in inherited for value in FEATURE_ADDITIONS), 'Policy already enabled in predecessor')
    command = [mapped(value) for value in prior['command']]
    command[0] = os.environ.get('NATIVE_APP_CC', command[0])
    before = list(command)
    if policy:
        command[command.index('-o'):command.index('-o')] = FEATURE_ADDITIONS
    require([value for value in command if value not in FEATURE_ADDITIONS] == before, 'Inherited target options changed')
    return command, inherited

def closure(command, flags, roots):
    dependencies = {}
    includes = [value for value in command if value.startswith('-I')]
    for source in [Path(value) for value in command if value.endswith('.c')]:
        output = subprocess.check_output([command[0], '-std=c11', '-Os', '-fPIC', '-ffreestanding', '-fno-builtin',
            '-MM', *flags, *includes, str(source)], text=True)
        for token in shlex.split(output.replace('\\\n',' ').split(':',1)[1]):
            path = Path(token).resolve()
            require(path.is_file() and not {'test','tests','fixtures'} & set(path.parts), 'Invalid target input: ' + token)
            owners = [(owner, path.relative_to(root)) for owner, root in roots.items() if path.is_relative_to(root)]
            require(len(owners) == 1, 'Unowned or ambiguous target source: ' + str(path))
            owner, relative = owners[0]
            dependencies[owner + ':' + relative.as_posix()] = {'sha256':sha(path), 'bytes':path.stat().st_size}
    return dependencies

def build(args):
    roots = {owner: getattr(args, name).resolve() for owner, name in [('system-apps','system'),
             ('utilities','utilities'),('productivity','productivity'),('runtime','runtime'),('watch','watch_profile'),('generated','output')]}
    pins = dict(load_selection()['sources'], productivity=args.productivity_commit)
    source_guard(roots, pins, args.provisional)
    recipe = git(ROOT, 'rev-parse', 'HEAD')
    if not args.provisional:
        require(not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Dirty public recipe')
    prior, manifest = selected_predecessor()
    out = roots['generated']
    require(not out.exists(), 'Use a fresh output directory')
    out.mkdir(parents=True)
    generated = {}
    for name, digest in PINNED['generated_sha256'].items():
        source = GENERATED/name
        require(sha(source) == digest, 'Changed selected generated input: ' + name)
        (out/name).write_text(relocate(source.read_text(), prior['source_roots'], roots))
        generated[name] = {'predecessor_sha256':digest,'selected_sha256':sha(out/name),'operation':'source-root relocation only'}
    for name, row in prior['target_dependencies'].items():
        owner, relative = name.split(':',1)
        if owner == 'watch':
            require(sha(roots[owner]/relative) == row['sha256'], 'Selected Watch profile changed: ' + name)
    command, inherited = command_for(prior, roots, not args.flag_off)
    flags = inherited + ([] if args.flag_off else FEATURE_ADDITIONS)
    compiler = subprocess.check_output([command[0], '--version'], text=True).splitlines()[0]
    require('8.4.0' in compiler and '2021r2-patch5' in compiler, 'Wrong target compiler')
    dependencies = closure(command, flags, roots)
    if not args.provisional:
        for owner in pins:
            tracked = set(git(roots[owner], 'ls-files').splitlines())
            require(all(name.split(':',1)[1] in tracked for name in dependencies if name.startswith(owner+':')),
                    'Untracked target input in public source: ' + owner)
    fonts = {name: row['sha256'] for name, row in prior['target_dependencies'].items()
             if any('/'+group+'/' in name for group in ('fonts','settings_fonts','paper_fonts','quick_fonts','home_fonts'))}
    require(fonts and all(name in dependencies and dependencies[name]['sha256'] == digest for name, digest in fonts.items()),
            'Inherited Points fonts changed or disappeared')
    if not args.flag_off:
        for name in ('PortableTextInputClient.h','PortableTextInputPolicy.h','PortableTextInputCheckpointClient.h'):
            require(any(key.endswith('/'+name) for key in dependencies), 'Missing modal dependency: ' + name)
    elf = out/'points_in_time.elf'
    attempts = compile_exact(command, elf, out/'debug/linker-attempts')
    system = roots['system-apps']
    validator = out/'validate-elf'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(system/'test/native_apps/stubs'),
        '-I'+str(system/'lib/elf_loader/include'),str(system/'lib/elf_loader/src/esp_elf_validate.c'),
        str(system/'test/native_apps/validate_test.c'),'-o',str(validator)], check=True)
    subprocess.run([str(validator),str(elf)],check=True)
    compaction = compact(elf,command[0],debug_path=out/'debug/points_in_time.elf')
    metadata_packing = None
    if not args.flag_off:
        shutil.copyfile(elf, out/'debug/points-before-metadata-pack.elf')
        packed, metadata_packing = pack_metadata(elf.read_bytes())
        elf.write_bytes(packed)
    subprocess.run([str(validator),str(elf)],check=True)
    nm = subprocess.check_output([command[0].removesuffix('gcc')+'nm','-D',str(elf)],text=True)
    imports = {line.split()[-1] for line in nm.splitlines() if ' U ' in ' '+line}
    exports = {line.split()[-1] for line in nm.splitlines() if len(line.split())>=3 and line.split()[-2] in ('T','D','B','R')}
    require(imports == set(prior['imports']) and exports == set(prior['exports']), 'Inherited Points ABI changed')
    require(b'ui.text-input\0' in elf.read_bytes(), 'Shared input service missing')
    for name,row in dependencies.items():
        owner, relative = name.split(':',1)
        require(sha(roots[owner]/relative)==row['sha256'],'Source changed during build: '+name)
    source_guard(roots, pins, args.provisional)
    require(git(ROOT,'rev-parse','HEAD') == recipe,'Recipe changed during target build')
    if not args.provisional:
        require(not git(ROOT,'status','--porcelain','--untracked-files=no'),'Public recipe changed during target build')
    manifest['version'] = '0.6.13' if args.flag_off else VERSION
    (out/'points_in_time.json').write_text(json.dumps(manifest,separators=(',',':'))+'\n')
    record = dict(schema='points.modal-policy.component.v1',device='watch',version=manifest['version'],sha256=sha(elf),
        bytes=elf.stat().st_size,manifest_sha256=sha(out/'points_in_time.json'),sources=pins,
        source_roots={name:str(path) for name,path in roots.items()},
        source_publication='local-provisional' if args.provisional else 'public-exact-commit',recipe_commit=recipe,
        recipe_sha256=sha(__file__),compiler=compiler,command=command,defines=flags,inherited_defines=inherited,
        feature_additions=[] if args.flag_off else FEATURE_ADDITIONS,target_dependencies=dependencies,
        generated_provenance=generated,original_font_sha256=fonts,original_fonts_retained=True,baseline_features_preserved=True,
        predecessor_record_sha256=PINNED['record_sha256'],predecessor_elf_sha256=PINNED['elf_sha256'],
        predecessor_bytes=prior['bytes'],delta_bytes=elf.stat().st_size-prior['bytes'],
        required_grants=prior['required_grants'],imports=sorted(imports),exports=sorted(exports),compaction=compaction,
        metadata_gap_packing=metadata_packing,linker_attempts=attempts,shared_text_input=True,modal_policy=not args.flag_off,native_changed=False,
        hardware_verified=False,target_instructions_executed=False,tonight_sealed_build_unchanged=True,
        flag_off_selected_predecessor_equal=sha(elf)==PINNED['elf_sha256'] if args.flag_off else None)
    (out/'points_in_time-build-record.json').write_text(json.dumps(record,indent=2)+'\n')
    print('Watch Points',manifest['version'],record['bytes'],record['sha256'],'delta',record['delta_bytes'])
    return record

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('system','utilities','productivity','runtime','watch-profile','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--productivity-commit',required=True)
    p.add_argument('--provisional',action='store_true',help='Local evidence only; never public qualification')
    p.add_argument('--flag-off',action='store_true')
    build(p.parse_args())
if __name__=='__main__': main()
