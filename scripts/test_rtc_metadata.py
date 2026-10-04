#!/usr/bin/env python3
"""Negative checks use the actual accepted/canonical RTC target ELF as oracle."""
import sys,struct
from pathlib import Path
from rtc_metadata import normalize,BASELINE_SHA,sha
base=Path(sys.argv[1]).read_bytes();assert sha(base)==BASELINE_SHA
same,record=normalize(base);assert same==base and not record['changed_bytes']
offset=record['string_offset']
changed=bytearray(base);changed[offset:offset+9]=b'days$2999'
fixed,proof=normalize(changed);assert fixed==base and proof['all_other_bytes_equal'] and proof['changed_bytes']
def reject(data):
 try:normalize(data)
 except (ValueError,struct.error):return
 raise AssertionError('Malformed or semantically changed RTC accepted')
for at in [0,18,52,len(base)-1]:
 bad=bytearray(changed);bad[at]^=1;reject(bad)
for label in [b'days$2bad',b'evil$2999',b'days$999\0']:
 bad=bytearray(changed);bad[offset:offset+9]=label;reject(bad)
# A changed symbol value/size/binding or any relocation/code byte must fail.
header=struct.unpack_from('<16sHHIIIIIHHHHHH',base)
for i in range(header[12]):
 section=struct.unpack_from('<IIIIIIIIII',base,header[6]+40*i)
 if section[1]==2:
  for field in [4,8,12]:
   bad=bytearray(changed);bad[section[4]+record['symbol_index']*16+field]^=1;reject(bad)
 if section[1] in (1,4) and section[5] and (section[2]&2 or section[1]==4):
  bad=bytearray(changed);bad[section[4]]^=1;reject(bad)
print('RTC metadata: exact full-baseline equality and code/relocation/header/symbol negative checks passed')
