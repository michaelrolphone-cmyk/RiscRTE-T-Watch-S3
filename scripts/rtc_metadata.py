"""Preserve immutable RTC0.2.0 bytes across GCC8 local declaration numbering.

Never waive code, section, relocation or other-byte differences: after changing
only the one validated non-loaded local symbol name, the ENTIRE file must equal
the accepted artifact's fixed SHA256. This is not a generic ELF normalizer.
"""
import hashlib,re,struct
BASELINE_SHA='28f7235841466a7028627c27460c31ce8c43520f55cf44650b26307e60371756'
BASELINE_NAME=b'days$2186'
def sha(data):return hashlib.sha256(data).hexdigest()
def normalize(data):
    if len(data)<52 or data[:7]!=b'\x7fELF\x01\x01\x01':raise ValueError('RTC requires ELF32 little-endian')
    header=struct.unpack_from('<16sHHIIIIIHHHHHH',data)
    if header[1:3]!=(3,94) or header[8]!=52 or header[11]!=40:raise ValueError('RTC ELF ABI mismatch')
    shoff,count,names_index=header[6],header[12],header[13]
    if not 0<count<=128 or names_index>=count or shoff+count*40>len(data):raise ValueError('RTC section bounds')
    sections=[struct.unpack_from('<IIIIIIIIII',data,shoff+i*40) for i in range(count)]
    for s in sections:
        if s[1]!=8 and s[4]+s[5]>len(data):raise ValueError('RTC section file bounds')
    def string(table,offset):
        if offset>=len(table):raise ValueError('RTC string bounds')
        end=table.find(b'\0',offset)
        if end<0:raise ValueError('RTC unterminated string')
        return table[offset:end]
    names=sections[names_index];table=data[names[4]:names[4]+names[5]]
    labels=[string(table,s[0]) for s in sections]
    if labels.count(b'.strtab')!=1 or labels.count(b'.symtab')!=1:raise ValueError('RTC unique symbol tables required')
    strings_index=labels.index(b'.strtab');strings=sections[strings_index];symbols=sections[labels.index(b'.symtab')]
    if strings[1]!=3 or strings[2]&2 or symbols[1]!=2 or symbols[6]!=strings_index or symbols[9]!=16 or symbols[5]%16:raise ValueError('RTC non-allocated static symbol table required')
    strings_data=data[strings[4]:strings[4]+strings[5]];matches=[]
    for index,at in enumerate(range(symbols[4],symbols[4]+symbols[5],16)):
        name,value,size,info,other,section=struct.unpack_from('<IIIBBH',data,at)
        label=string(strings_data,name)
        if not label.startswith(b'days$'):continue
        if not re.fullmatch(rb'days\$[0-9]{4}',label) or info!=1 or other or size!=12 or section>=count or labels[section]!=b'.rodata':raise ValueError('RTC local calendar object mismatch')
        rodata=sections[section];relative=value-rodata[3]
        if not rodata[2]&2 or relative<0 or relative+12>rodata[5] or data[rodata[4]+relative:rodata[4]+relative+12]!=bytes([31,28,31,30,31,30,31,31,30,31,30,31]):raise ValueError('RTC calendar data mismatch')
        matches.append((index,strings[4]+name,label))
    if len(matches)!=1:raise ValueError('RTC expected exactly one numbered local calendar symbol')
    index,offset,label=matches[0]
    phoff,entry_size,phcount=header[5],header[9],header[10]
    if entry_size!=32 or phcount>128 or phoff+phcount*entry_size>len(data):raise ValueError('RTC program header bounds')
    for at in range(phoff,phoff+phcount*entry_size,entry_size):
        program=struct.unpack_from('<IIIIIIII',data,at)
        if program[0]==1 and offset<program[1]+program[4] and offset+len(label)>program[1]:raise ValueError('RTC label overlaps PT_LOAD')
    result=bytearray(data)
    result[offset:offset+len(BASELINE_NAME)]=BASELINE_NAME
    if sha(result)!=BASELINE_SHA:raise ValueError('RTC differs beyond the allowed local metadata label: '+sha(data))
    return bytes(result),{'baseline_sha256':BASELINE_SHA,'compiled_sha256':sha(data),'packaged_sha256':sha(result),'symbol_index':index,'string_offset':offset,'compiled_label':label.decode(),'packaged_label':BASELINE_NAME.decode(),'changed_bytes':[i for i,(a,b) in enumerate(zip(data,result)) if a!=b],'all_other_bytes_equal':True,'outside_pt_load':True}
