import copy
import hashlib
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import current_bootfs as bootfs
import current_cohort as cohort
import current_flash_layout as flash
import expanded_layout as expanded
from read_only_spiffs import read_image

class ExpandedLayout(unittest.TestCase):
    firmware=b'\xe9'+b'RISC_PAIRED_STORE_ABI:3\0'+b'RISC_RUNTIME_VERSION:0.2.67\0'+b'x'*32
    def deployment(self):
        return dict(layout=expanded.LAYOUT,target='esp32s3-16mb-appdata-expanded-iq',radio_iq=True,
                    store_abi=3,flash_bytes=0x1000000,partitions=copy.deepcopy(expanded.DEPLOYMENT_PARTS),
                    factory_warning=expanded.FACTORY_WARNING)
    def test_partition_table_complete_and_exact(self):
        table=expanded.partition_table();self.assertEqual(len(table),3072)
        expanded.verify_partition_table(table)
        self.assertEqual(len(expanded.PARTITIONS),8)
        self.assertEqual(expanded.PARTITIONS['appdata'][2:],(0x270000,0x80000))
        self.assertEqual(expanded.PARTITIONS['bootfs0'][2]+expanded.STORE_BYTES,0x840000)
        self.assertEqual(expanded.PARTITIONS['app1'][2]+expanded.PARTITIONS['app1'][3],0xaa0000)
        self.assertEqual(expanded.PARTITIONS['bootfs1'][2]+expanded.STORE_BYTES,0xff0000)
        for at in (0,32,255,270,3000):
            bad=bytearray(table);bad[at]^=1
            with self.assertRaises(ValueError):expanded.verify_partition_table(bad)
    def test_cohort_explicit_and_abi_marker_fail_closed(self):
        identity=cohort.create('1.2.3','0.2.67','a'*40,self.firmware,expanded=True)
        self.assertEqual(cohort.parse(cohort.encode(identity,expanded=True),expanded=True),identity)
        with self.assertRaises(ValueError):cohort.validate(identity)
        old=cohort.create('1.2.3','0.2.67','a'*40,self.firmware)
        with self.assertRaises(ValueError):cohort.validate(old,expanded=True)
        for marker in (b'RISC_PAIRED_STORE_ABI:1\0',b'RISC_PAIRED_STORE_ABI:2\0',b'RISC_OWNER_INSTALLER:1\0'):
            with self.assertRaises(ValueError):cohort.create('1.2.3','0.2.67','a'*40,self.firmware+marker,expanded=True)
        with self.assertRaises(ValueError):cohort.create('1.2.3','0.2.67','a'*40,b'old'*40,expanded=True)
    def test_store_roundtrip_and_cohort_payload_extents(self):
        identity=cohort.create('1.2.3','0.2.67','a'*40,self.firmware,expanded=True)
        files={'cohort.json':cohort.encode(identity,expanded=True),'sentinel':b'unchanged data'}
        store,record=bootfs.build(files,size=expanded.STORE_BYTES)
        self.assertEqual(read_image(store,expanded.STORE_BYTES),files)
        self.assertEqual(record['image_bytes'],expanded.STORE_BYTES)
        payload,ota=cohort.package(identity,self.firmware,store,expanded=True)
        self.assertEqual(payload,self.firmware+store)
        self.assertEqual(ota['store_abi'],3);self.assertEqual(ota['store_size'],0x550000)
        self.assertEqual(ota['size'],len(self.firmware)+0x550000)
        with self.assertRaises(ValueError):cohort.package(identity,self.firmware,store[:-1],expanded=True)
        old_store,_=bootfs.build({'sentinel':b'old'})
        self.assertEqual(len(old_store),0x510000)
        with self.assertRaises(ValueError):cohort.package(identity,self.firmware,old_store,expanded=True)
    def test_factory_warning_metadata_and_erased_regions(self):
        store=b'\x99'*expanded.STORE_BYTES;data=b'\xcc'*0x80000
        parts={'bootloader.bin':b'loader','partitions.bin':expanded.partition_table(),
               'firmware.bin':self.firmware,'bootfs.bin':store,'appdata.bin':data,
               'otadata.bin':expanded.initial_otadata(),'bank_state.bin':expanded.initial_bank_state(self.firmware,store)}
        with patch('current_flash_layout.APP_DATA_SHA',hashlib.sha256(data).hexdigest()):
            image,entries=flash.assemble(parts,self.deployment(),True)
            self.assertEqual(len(image),0x1000000);self.assertEqual(len(entries),7)
            self.assertEqual(image[0x270000:0x2f0000],data)
            self.assertEqual(image[0x2f0000:0x840000],store)
            for start,end in ((0x9000,0xf000),(0x840000,0xff0000),(0xff4000,0x1000000)):
                self.assertEqual(image[start:end],b'\xff'*(end-start))
            self.assertEqual(struct.unpack_from('<6I',image,0xff2000),(0x314b4252,1,0,len(self.firmware),0x550000,3))
            bad=self.deployment();bad.pop('factory_warning')
            with self.assertRaises(ValueError):flash.assemble(parts,bad,True)
            for name in ('partitions.bin','otadata.bin','bank_state.bin'):
                bad=bytearray(parts[name]);bad[0]^=1
                with self.assertRaises(ValueError):flash.assemble({**parts,name:bytes(bad)},self.deployment(),True)
            for name in ('firmware.bin','bootfs.bin','appdata.bin'):
                with self.assertRaises(ValueError):flash.assemble({**parts,name:parts[name]+b'x'},self.deployment(),True)
            bad=self.deployment();bad['partitions']['app1']['offset']=0x800000
            with self.assertRaises(ValueError):flash.assemble(parts,bad,True)
if __name__=='__main__':unittest.main()
