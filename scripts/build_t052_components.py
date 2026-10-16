from pathlib import Path
from types import SimpleNamespace
import json,subprocess,sys,hashlib
R=Path(__file__).resolve().parents[2];S=R/'System-t052';O=R/'t052-build'
sys.path.insert(0,str(S/'scripts'));from portable_file_sharing_build import configure
sys.path.insert(0,'/tmp/waveshare-generic-bridges/scripts');from normalize_xtensa_relocations import normalize
from compact_current_elf import compact
c=json.loads((R/'t051-product-build/watch-wifi-command.json').read_text());c=[s.replace(str(R/'System-watch-t051'),str(S)) for s in c]
c=[s for s in c if not s.startswith(('-DPORTABLE_WIFI_','-DWIFI_RETURN_APP='))]
c=[str(S/'Apps/file_browser.c') if s.endswith('/Apps/wifi_settings.c') else s for s in c]
common=['-DPORTABLE_FILE_BROWSER_APP','-DPORTABLE_APP_OWNS_TOUCH_CHROME','-DPORTABLE_FILE_BROWSER_RGB_ONLY','-DPORTABLE_FILE_BROWSER_CAPABILITY="storage.installed-files"','-DPORTABLE_FILE_BROWSER_INSTANCE=0','-DPORTABLE_FILE_BROWSER_SECONDARY_CAPABILITY="storage.app-data.export"','-DPORTABLE_FILE_BROWSER_SECONDARY_INSTANCE=0','-DPORTABLE_FILE_BROWSER_SOURCE_HANDOFF','-DPORTABLE_FILE_BROWSER_SHARED_INPUT','-DPORTABLE_TEXT_INPUT_POLICY','-DPORTABLE_FILE_BROWSER_HANDLERS','-DFILE_BROWSER_RETURN_APP="springboard.elf"','-DPORTABLE_WIFI_INSTANCE=15','-DPORTABLE_DISPLAY_ROTATION=0']
profile=SimpleNamespace(peer_files=True,webdav_sharing=True,sharing_export_instance=0,sharing_tcp_instance=0,sharing_entropy_instance=0,sharing_setup_instance=0)
flags,sources,_=configure(profile,S,O,S/'lib/PortableApps/include',c[0]);existing={str(x) for x in c};sources=[str(s) for s in sources if str(s) not in existing]
for product,extra in [('watch',[]),('waveshare',['-DPORTABLE_FILE_BROWSER_TERTIARY_CAPABILITY="storage.volume"','-DPORTABLE_FILE_BROWSER_TERTIARY_INSTANCE=12'])]:
 d=O/product;d.mkdir(exist_ok=True);elf=d/'file_browser.elf';cmd=c+common+flags+sources+extra;cmd[cmd.index('-o')+1]=str(elf)
 (d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 with (d/'build.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
 normalize(elf);proof=compact(elf,c[0],debug_path=d/'file_browser.debug.elf');subprocess.run([str(R.parent/'task-2/target-providers/validate-elf'),str(elf)],check=True)
 (d/'build.json').write_text(json.dumps(dict(sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),bytes=elf.stat().st_size,compaction=proof,system_source=subprocess.check_output(['git','-C',S,'rev-parse','HEAD'],text=True).strip(),version='1.5.38'),indent=2)+'\n');print(product,elf.stat().st_size)
