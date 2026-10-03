#!/usr/bin/env python3
"""Embed board catalogs; no device I/O, filesystem mutation outside dist."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def generate():
    out=ROOT/'dist/generated';out.mkdir(parents=True,exist_ok=True)
    rows=[];parts=['/* Generated from hardware JSON; do not edit. */']
    for i,p in enumerate(sorted((ROOT/'hardware').glob('*.json'))):
        m=json.loads(p.read_text());text=json.dumps(m,separators=(',',':'))
        parts.append(f'static const char manifest_{i}[]='+json.dumps(text)+';')
        rows.append('{1,sizeof(risc_hardware_catalog_v1),'+json.dumps(m['board_id'])+','+json.dumps(m['revision'])+f',manifest_{i},sizeof(manifest_{i})-1'+'}')
    parts.append('static const risc_hardware_catalog_v1 catalogs[]={'+','.join(rows)+'};')
    (out/'board_catalogs.h').write_text('\n'.join(parts)+'\n')
    return out
if __name__=='__main__':generate()
