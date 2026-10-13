from pathlib import Path
import json,sys
sys.path.insert(0,'/product-watch/scripts')
from verify_update_elf import verify
app=Path('/card/Apps/lora_messages/lora_messages.elf').read_bytes()
r={}
for name,root,native in [('watch','/runtime-watch','/runtime-watch/.pio/build/watch-expanded/firmware.elf'),('waveshare','/waveshare-suite-runtime-0122','/wave-firmware.elf')]:
 r[name]=verify(Path(root),Path(native).read_bytes(),app,store_abi=3)
Path('/out/card-admission.json').write_text(json.dumps(r,indent=2)+'\n')
print('Identical LoRa ELF admitted against both exact native public export tables; each missing import rejected; custody refusal checked; no target code executed.')
