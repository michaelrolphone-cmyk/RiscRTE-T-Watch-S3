#!/usr/bin/env python3
"""Relocate non-allocated ELF tail metadata into an existing unmapped file gap.

All program headers, allocated bytes/addresses/alignments, symbols, relocations,
section order and entrypoint remain unchanged. Only e_shoff and non-allocated
section file offsets move. The retained loader evidence must compare exactly.
This does not change linker options or the separately retained debug ELF.
"""
import argparse
import io
import json
from pathlib import Path
import struct

from elftools.elf.elffile import ELFFile
from compact_current_elf import evidence, sha
from build_lora_policy import require

PROFILE='points-nonallocated-tail-gap-v1'

def align(value, alignment):
    require(alignment == 0 or alignment & (alignment-1) == 0, 'Invalid section alignment')
    return (value + max(1,alignment)-1) & ~(max(1,alignment)-1)

def pack(data):
    elf=ELFFile(io.BytesIO(data))
    require(elf.elfclass==32 and elf.little_endian and elf['e_machine']=='EM_XTENSA' and elf['e_type']=='ET_DYN',
            'Expected ELF32 little-endian Xtensa shared object')
    require(elf['e_shentsize']==40 and elf['e_phentsize']==32, 'Unexpected ELF table layout')
    before=evidence(data)
    sections=list(elf.iter_sections())
    segments=list(elf.iter_segments())
    ranges=sorted((s['p_offset'],s['p_offset']+s['p_filesz']) for s in segments if s['p_filesz'])
    require(ranges, 'Missing mapped segments')
    merged=[]
    for start,end in ranges:
        require(0<=start<=end<=len(data),'Invalid segment range')
        if merged and start<=merged[-1][1]:
            merged[-1]=(merged[-1][0],max(merged[-1][1],end))
        else:
            merged.append((start,end))
    tail=merged[-1][1]
    metadata=[]
    for index,section in enumerate(sections):
        if section['sh_type'] in ('SHT_NULL','SHT_NOBITS') or not section['sh_size']:
            continue
        start,end=section['sh_offset'],section['sh_offset']+section['sh_size']
        require(end<=len(data), 'Invalid section range')
        if start>=tail:
            require(not section['sh_flags'] & 2, 'Allocated tail section cannot move')
            metadata.append((index,section))
        else:
            require(end<=tail, 'Section straddles metadata tail')
    require(metadata and elf['e_shoff']>=tail and elf['e_shoff']+len(sections)*40<=len(data),
            'Expected entirely non-allocated metadata suffix')
    placements=None
    for (_,start),(end,_) in zip(merged,merged[1:]):
        require(start<=end, 'Overlapping segment gap')
        occupied=[s for s in sections if s['sh_type'] not in ('SHT_NULL','SHT_NOBITS') and s['sh_size'] and
                  s['sh_offset']<end and s['sh_offset']+s['sh_size']>start]
        if occupied:
            continue
        cursor=start;rows=[]
        for index,section in metadata:
            cursor=align(cursor,section['sh_addralign'])
            rows.append((index,section,cursor));cursor+=section['sh_size']
        table=align(cursor,4)
        if table+len(sections)*40<=end:
            placements=(start,end,rows,table)
            break
    require(placements, 'No unmapped file gap can hold complete metadata suffix')
    start,end,rows,table=placements
    result=bytearray(data[:tail])
    section_table=bytearray(data[elf['e_shoff']:elf['e_shoff']+len(sections)*40])
    changes=[]
    for index,section,offset in rows:
        result[offset:offset+section['sh_size']]=section.data()
        struct.pack_into('<I',section_table,index*40+16,offset)
        changes.append(dict(section=section.name,before_offset=section['sh_offset'],after_offset=offset,
                            bytes=section['sh_size'],section_alignment=section['sh_addralign']))
    result[table:table+len(section_table)]=section_table
    struct.pack_into('<I',result,32,table)
    result=bytes(result)
    require(evidence(result)==before, 'Metadata packing changed retained loader evidence')
    require(result[elf['e_phoff']:elf['e_phoff']+elf['e_phnum']*32] ==
            data[elf['e_phoff']:elf['e_phoff']+elf['e_phnum']*32], 'Program headers changed')
    require(len(result)<len(data), 'Metadata packing did not reduce file bytes')
    return result, dict(profile=PROFILE,before_bytes=len(data),after_bytes=len(result),bytes_saved=len(data)-len(result),
        before_sha256=sha(data),after_sha256=sha(result),gap_start=start,gap_end=end,gap_bytes=end-start,
        section_table_before=elf['e_shoff'],section_table_after=table,metadata_moves=changes,
        retained_loader_evidence_identical=True,program_headers_byte_identical=True,
        allocated_sections_bytes_addresses_alignments_identical=True,imports_exports_and_relocations_identical=True,
        section_inventory_and_order_identical=True,linker_options_unchanged=True,
        section_file_offsets_changed_only_for_nonallocated_metadata=True,
        target_instructions_executed=False,hardware_verified=False)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True)
    args=p.parse_args()
    require(not args.output.exists() and not args.receipt.exists(), 'Use fresh diagnostic outputs')
    result,proof=pack(args.input.read_bytes())
    args.output.write_bytes(result)
    args.receipt.write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof,indent=2))
if __name__=='__main__': main()
