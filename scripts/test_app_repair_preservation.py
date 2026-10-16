#!/usr/bin/env python3
"""Offline preservation/fault model for exact .36 and a composed candidate store.
All flash bytes are software fixtures. No serial, hardware or publication access.
"""
import argparse,hashlib,json,struct,sys
from pathlib import Path
from watch_app_repair import PINS,need,sha,encoded

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('runtime','baseline','firmware','store','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();sys.path.insert(0,str(a.runtime/'scripts'))
 from prepare_preserving_update import layout,pair,plan,selection,ota
 from paired_bank_images import initial_bank_state,record
 baseline=a.baseline.read_bytes();need(sha(baseline)==PINS['baseline_sha256'],'Wrong .36 factory')
 geometry=layout(baseline);expanded,natives,stores,size=geometry;need(expanded and size==0x550000,'Wrong ABI3 geometry')
 firmware=a.firmware.read_bytes();store=a.store.read_bytes();need(len(store)==size and len(firmware)<=0x260000,'Invalid candidate lengths')
 _,old_fw,old_store=pair(baseline,0,geometry)
 candidate=bytearray(baseline);candidate[natives[0]:natives[0]+0x260000]=firmware+b'\xff'*(0x260000-len(firmware));candidate[stores[0]:stores[0]+size]=store
 state=initial_bank_state(firmware,store,True,True);candidate[0xff2000:0xff2000+len(state)]=state
 pair(candidate,0,geometry)
 cases=[]
 def active(image):
  rows=[(row[0],i) for i in range(2) if (row:=ota(image[0xff0000+i*4096:0xff0020+i*4096]))]
  return (max(rows)[0]-1)%2
 def protected(before,after,ranges):
  need(all(before[start:stop]==after[start:stop] for start,stop in ranges),'A protected region changed')
 for bank in (0,1):
  for selector_sector,both_valid in ((0,False),(1,False),(0,True),(1,True)):
   case_start=len(cases)
   snapshot=bytearray(baseline)
   snapshot[natives[bank]:natives[bank]+len(old_fw)]=old_fw;snapshot[stores[bank]:stores[bank]+size]=old_store
   snapshot[0xff2000+bank*4096:0xff3000+bank*4096]=record(bank,old_fw,old_store,True,True)+b'\xff'*(4096-96)
   sequence=bank+3
   snapshot[0xff0000:0xff2000]=b'\xff'*8192
   selection_offset=0xff0000+selector_sector*4096
   snapshot[selection_offset:selection_offset+4096]=selection(sequence,2)
   if both_valid:
    older=0xff0000+(1-selector_sector)*4096;snapshot[older:older+4096]=selection(sequence-1,2)
   snapshot[0x9000:0xf000]=bytes(range(256))*96
   snapshot[0x270000:0x2f0000]=bytes(reversed(range(256)))*2048
   need(active(snapshot)==bank,'Fixture selection mismatch')
   rows,receipt=plan(snapshot,baseline,candidate,PINS['baseline_sha256']);need(receipt['target_bank']==1-bank,'Wrong inactive target')
   need([r[0] for r in rows]==['firmware.bin','store.bin','bank-state.bin','ota-selection-LAST.bin'],'Selection must be last')
   for interrupted in (0,1,2,3):
    staged=bytearray(snapshot)
    for _,off,data in rows[:interrupted]:staged[off:off+len(data)]=data
    protected(snapshot,staged,receipt['preserved_ranges']);need(active(staged)==bank,'Pre-selection interruption changed active bank');pair(staged,bank,geometry)
    cases.append({'active_bank':bank,'completed_writes':interrupted,'old_pair_valid':True,'protected_ranges_unchanged':True})
   # Interrupt within each pre-selection erase/write. The old pair must still boot.
   for index in range(3):
    name,off,data=rows[index]
    for cut in (0,1,len(data)//2,len(data)-1):
     partial=bytearray(snapshot)
     for _,earlier,payload in rows[:index]:partial[earlier:earlier+len(payload)]=payload
     erased=(len(data)+4095)//4096*4096;partial[off:off+erased]=b'\xff'*erased
     partial[off:off+cut]=data[:cut];protected(snapshot,partial,receipt['preserved_ranges'])
     need(active(partial)==bank,'Torn inactive payload changed selection');pair(partial,bank,geometry)
     cases.append({'active_bank':bank,'torn_write':name,'bytes_written':cut,'old_pair_valid':True})
   # The final selector may be torn; either the old confirmed pair or the fully
   # staged candidate must remain valid. Selection is never attempted early.
   ready=bytearray(snapshot)
   for _,off,data in rows[:3]:ready[off:off+len(data)]=data
   name,off,data=rows[3]
   for cut in (0,1,28,31,32,4095):
    partial=bytearray(ready);partial[off:off+4096]=b'\xff'*4096;partial[off:off+cut]=data[:cut]
    protected(snapshot,partial,receipt['preserved_ranges']);selected=active(partial);pair(partial,selected,geometry)
    cases.append({'active_bank':bank,'torn_selection_bytes':cut,'selected_pair_valid':True})
   for index in (0,1):
    corrupt=bytearray(ready);corrupt[rows[index][1]+32]^=1
    try:pair(corrupt,1-bank,geometry)
    except ValueError:cases.append({'active_bank':bank,'readback_corruption':rows[index][0],'rejected_before_selection':True})
    else:raise ValueError('Corrupt staged pair passed readback')
   staged=bytearray(snapshot)
   for _,off,data in rows:staged[off:off+len(data)]=data
   protected(snapshot,staged,receipt['preserved_ranges']);need(active(staged)==1-bank,'Candidate not selected last')
   _,new_fw,new_store=pair(staged,1-bank,geometry);need(new_fw==firmware and new_store==store,'Selected pair differs from candidate')
   cases.append({'active_bank':bank,'completed_writes':4,'candidate_pair_valid':True,'nvs_and_appdata_preserved':True})
   for fault in ('active-native-corrupt','active-store-corrupt','not-confirmed','partition-change','wrong-baseline-digest','active-bank-state-corrupt','valid-but-wrong-active','equal-sequences','sequence-limit'):
    bad=bytearray(snapshot);digest=PINS['baseline_sha256']
    if fault=='active-native-corrupt':bad[natives[bank]+32]^=1
    elif fault=='active-store-corrupt':bad[stores[bank]+32]^=1
    elif fault=='not-confirmed':bad[selection_offset:selection_offset+4096]=selection(sequence,0)
    elif fault=='partition-change':bad[0x8000+4]^=1
    elif fault=='active-bank-state-corrupt':bad[0xff2000+bank*4096+92]^=1
    elif fault=='valid-but-wrong-active':
     other=bytearray(old_fw);other[32]^=1;bad[natives[bank]:natives[bank]+len(other)]=other
     bad[0xff2000+bank*4096:0xff2060+bank*4096]=record(bank,other,old_store,True,True)
    elif fault=='equal-sequences':bad[0xff0000:0xff2000]=selection(sequence,2)*2
    elif fault=='sequence-limit':bad[selection_offset:selection_offset+4096]=selection(0xfffffffe,2)
    else:digest='0'*64
    try:plan(bad,baseline,candidate,digest)
    except ValueError:cases.append({'active_bank':bank,'fault':fault,'rejected':True})
    else:raise ValueError('Unsafe fixture accepted: '+fault)
   for case in cases[case_start:]:case.update(selected_ota_sector=selector_sector,two_valid_selectors=both_valid)
 report={'baseline_version':'1.1.36','baseline_sha256':sha(baseline),'candidate_native_sha256':sha(firmware),'candidate_store_sha256':sha(store),'cases':cases,'software_fixtures_only':True,'device_accessed':False,'hardware_tested':False,'assets_published':False}
 a.output.mkdir(parents=True,exist_ok=False);(a.output/'preservation.json').write_bytes(encoded(report));print('PASS:',len(cases),'both-bank preservation/interruption/rejection fixtures; all NVS/AppData and active-pair ranges preserved')
if __name__=='__main__':main()
