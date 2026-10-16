#!/usr/bin/env python3
"""Reject unauthorized changes to the actual built Watch20 candidate in memory."""
import argparse
import json
from pathlib import Path
from build_touchpad_increment import scope, CHANGED, encoded
import watch_native_binding as binding
p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
before=binding.files_at(a.baseline);after=binding.files_at(a.candidate/'files');head=json.loads(after['cohort.json'])['source_revision']
scope(before,after,head);refused=[]
def reject(label, bad):
    try:scope(before,bad,head)
    except ValueError:refused.append(label)
    else:raise ValueError('Invalid candidate accepted: '+label)
for n in sorted(set(after)-CHANGED):reject('changed-preserved:'+n,{**after,n:after[n]+b'\n'})
reject('added-member',{**after,'extra.json':b'{}'})
for n in CHANGED:
    reject('omitted-change:'+n,{**after,n:before[n]})
for n in ('ble_touchpad.json','ble_buttons.json','ble-hid/manifest.json'):
    altered=json.loads(after[n]);altered['requires'].append({'capability':'unapproved.capability','api':1})
    reject('authority:'+n,{**after,n:encoded(altered)})
identity=json.loads(after['cohort.json']);identity['runtime_version']='0.1.74'
reject('runtime-version',{**after,'cohort.json':encoded(identity)})
a.output.write_bytes(encoded({'schema':1,'source_revision':head,'input_files':binding.inventory(after),'refused':refused,'refusals':len(refused),'accepted_exact_candidate':True,'inputs_modified':False}))
print(str(len(refused))+' actual-candidate scope mutations refused')
