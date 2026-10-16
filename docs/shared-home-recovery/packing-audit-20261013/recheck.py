#!/usr/bin/env python3
"""Read-only bounded capacity experiment; no selected layout or firmware output."""
import hashlib, importlib.util, json, os, pathlib, subprocess, tempfile
P=pathlib.Path
OUT=P('/workspace/shared/twatch-packer-recheck-20261013')
ROOT=P('/workspace/shared/twatch-shared-integration-20261013')
CROOT=P('/workspace/shared/watch-spiffs-profile-20261012')
ORIGINAL=P('/workspace/shared/twatch-shared-capacity-20261013/measure-home-catalog-ui.py')
PREVIOUS=ORIGINAL.with_name('home-catalog-ui-capacity.json')
sha=lambda b:hashlib.sha256(b).hexdigest()
os.environ['GIT_NO_LAZY_FETCH']='1'
before={str(p):sha(p.read_bytes()) for p in [ORIGINAL,PREVIOUS,ROOT/'scripts/current_bootfs.py',ROOT/'scripts/read_only_spiffs.py']}
prior=json.loads(PREVIOUS.read_bytes())
text=ORIGINAL.read_text(); marker='# The metadata source is not finally selected.'
assert text.count(marker)==1
prefix=text.split(marker)[0]
ns={'__file__':str(ORIGINAL),'__name__':'watch_exact_measurement_reconstruction'}
exec(compile(prefix,str(ORIGINAL), 'exec'),ns)
assert ns['cases']==prior['cases'], 'Prior exact capacity cases no longer reproduce'
selected=ns['candidate']
case_name='nonselected_lossless_ui_full_legacy_presentation_and_generic_grants_compact_json'
assert ns['measured'](selected)==prior['cases'][case_name]
analytical=prior['cases'][case_name]
manifest={n:{'bytes':len(b),'sha256':sha(b)} for n,b in sorted(selected.items())}
config=ns['capacity'].__globals__['CONFIG']
genpath=ROOT/'vendor/esp-idf-spiffs/spiffsgen.py'
spec=importlib.util.spec_from_file_location('measure_pinned_generator',genpath)
gen=importlib.util.module_from_spec(spec);spec.loader.exec_module(gen)
# Only the local measurement decoder guard is generalized for the explicitly
# nonselected 0x550000 experiment; existing product source remains byte-identical.
reader_path=ROOT/'scripts/read_only_spiffs.py'; decoder_source=reader_path.read_text()
assert decoder_source.count('assert expected_size in (0x4f0000, 0x510000)')==1
decoder_source=decoder_source.replace('assert expected_size in (0x4f0000, 0x510000)',
 'assert expected_size in (0x4f0000, 0x510000, 0x550000)')
decoder={};exec(compile(decoder_source,'<measurement-only-generalized-reader>','exec'),decoder)
read=decoder['read_image']

def count(image):
 live=deleted=free=empty=occupied=0
 for pos in range(0,len(image),4096):
  ids=[int.from_bytes(image[pos+i*2:pos+i*2+2],'little') for i in range(15)]
  live+=sum(x not in (0,65535) for x in ids)
  deleted+=ids.count(0);free+=ids.count(65535)
  empty+=all(x==65535 for x in ids);occupied+=any(x!=65535 for x in ids)
 return dict(live_pages=live,deleted_pages=deleted,free_pages=free,empty_blocks=empty,occupied_blocks=occupied)

result={'scope':'Measurement only; old exact Home/UI/catalog selection; no newer Contexts/full scene; no selected geometry, profile, app, firmware or store output',
 'prior_cases_reproduced_exactly':True,'old_report_sha256':before[str(PREVIOUS)],
 'analytical_case':case_name,'analytical':analytical,'exact_input_manifest':manifest,
 'baseline_sha256':prior['baseline_sha256'], 'generator_sha256':sha(genpath.read_bytes()),
 'direct_generator_config':config,'chunk_bytes':8192,'selected_layout_changed':False,
 'hypothetical_geometry_authorized_or_selected':False,'publication_performed':False,
 'tests':{}}
inputs=[OUT/'chunked_store_probe.c',ORIGINAL,genpath,*sorted((CROOT/'src').glob('*')),*sorted((CROOT/'shim').glob('*'))]
result['source_sha256']={str(p):sha(p.read_bytes()) for p in inputs if p.is_file()}
with tempfile.TemporaryDirectory(prefix='twatch-packer-recheck-',dir='/tmp') as td:
 tmp=P(td);binary=tmp/'chunked_store_probe'
 command=['cc','-O2','-Wall','-Wextra','-I'+str(CROOT/'shim'),'-I'+str(CROOT/'src'),str(OUT/'chunked_store_probe.c')]+[str(CROOT/'src'/('spiffs_'+n+'.c')) for n in ['cache','check','gc','hydrogen','nucleus']]+['-o',str(binary)]
 compiled=subprocess.run(command,text=True,capture_output=True,check=True)
 assert not compiled.stderr, compiled.stderr
 result['compile_command']=command;result['compiler_version']=subprocess.check_output(['cc','--version'],text=True).splitlines()[0]
 result['probe_binary_sha256']=sha(binary.read_bytes())
 data_dir=tmp/'input';data_dir.mkdir(); listing=tmp/'list.txt'; output=tmp/'measurement-only.img'
 for selection_name,store in [('recovered_exact',ns['old']),('old_compact_home_ui_catalog',selected)]:
  for n,b in sorted(store.items()):
   file=data_dir/n;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b)
  listing.write_text(''.join(n+'\n' for n in sorted(store)))
  sizes=[0x510000] if selection_name=='recovered_exact' else [0x510000,0x550000]
  for size in sizes:
   key=selection_name+'_'+hex(size)
   packed=subprocess.run([str(binary),str(size),str(data_dir),str(listing),str(output)],text=True,capture_output=True,check=True,timeout=90)
   packing=json.loads(packed.stdout);assert not packed.stderr,packed.stderr
   image=output.read_bytes();assert len(image)==size
   packing['measurement_image_sha256']=sha(image);packing['measurement_image_persisted']=False
   packing['independent_page_scan']=count(image)
   assert packing['live_pages']==packing['independent_page_scan']['live_pages']
   assert packing['deleted_pages']==packing['independent_page_scan']['deleted_pages']
   decoded=read(image,size)
   packing['independent_decoded_file_count']=len(decoded)
   packing['independent_exact_complete_input_readback']=decoded==store
   packing['decoded_matching_whole_file_count']=sum(decoded.get(n)==b for n,b in store.items())
   packing['hypothetical_geometry']=size!=0x510000
   if not packing['error']:assert decoded==store
   result['tests'][key]={'chunked_c_packer':packing}
   fs=gen.SpiffsFS(size,gen.SpiffsBuildConfig(**config))
   error=None
   try:
    for n in sorted(store):fs.create_file('/'+n,str(data_dir/n))
   except Exception as ex:error=type(ex).__name__+': '+str(ex)
   direct={'error':error,'blocks_allocated':len(fs.blocks),'remaining_blocks':fs.remaining_blocks}
   if error is None:
    image=fs.to_binary();assert len(image)==size;assert read(image,size)==store
    direct.update(count(image));direct['independent_exact_complete_input_readback']=True
    direct['measurement_image_sha256']=sha(image);direct['measurement_image_persisted']=False
   result['tests'][key]['pinned_direct_page_generator']=direct
   print(json.dumps({key:result['tests'][key]},sort_keys=True),flush=True)
   output.unlink()
for p,digest in before.items():assert sha(P(p).read_bytes())==digest,p
result['prior_report_and_product_scripts_unchanged']=True
result['temporary_test_inputs_and_images_removed']=True
result['measurement_script_sha256']=sha(P(__file__).read_bytes())
(OUT/'recheck-results.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print('RESULT '+str(OUT/'recheck-results.json'),flush=True)
