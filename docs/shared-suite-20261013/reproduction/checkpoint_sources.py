from pathlib import Path
import subprocess,json,hashlib
R=Path(__file__).resolve().parent;out=R/'recovery';out.mkdir(exist_ok=True)
repos={'watch-runtime':'/tmp/twatch-capacity-runtime-0121','wave-runtime':'/tmp/waveshare-suite-runtime-0122','watch-product':'/tmp/twatch-shared-cohort-0121','wave-product':'/tmp/waveshare-shared-cohort-0121','home':'/tmp/shared-home-media-0122','home-system':'/tmp/shared-home-system-media-0122','lora':'/tmp/twatch-lora-shared-0121'}
records={}
for key,path in repos.items():
 def git(*args):return subprocess.check_output(['git','-C',path,*args])
 assert not git('diff','HEAD','--name-only').strip()
 pin=git('rev-parse','HEAD').decode().strip();dest=out/(key+'-source.tar.gz')
 subprocess.run(['git','-C',path,'archive','--format=tar.gz','--prefix='+key+'/', '-o',str(dest),'HEAD'],check=True)
 records[key]={'path':path,'source':pin,'archive':dest.name,'bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'status':git('status','--short').decode()}
# Native Waveshare build intentionally stages this exact vendor source and profile.
staged={}
for p in [Path('/tmp/waveshare-suite-runtime-0122/expanded-candidate.ini'),Path('/tmp/waveshare-suite-runtime-0122/src/VendorDisplay.cpp'),*Path('/tmp/waveshare-suite-runtime-0122/lib/WaveshareVendorGfx').rglob('*')]:
 if p.is_file():staged[str(p.relative_to('/tmp/waveshare-suite-runtime-0122'))]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
records['waveshare-native-staging']={'vendor_pin':'b099739ad0e33b34e5fbaae77f02bd84805d79a3','files':staged}
(out/'source-checkpoints.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps({k:v.get('source') for k,v in records.items()},indent=2))
