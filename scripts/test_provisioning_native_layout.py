#!/usr/bin/env python3
"""Linked native layout proof, including missing/changed debug and storage evidence."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from build_provisioning_native import linked_provisioning_layout, provisioning_compile_selection


class LinkedLayout(unittest.TestCase):
    def test_exact_runtime_compile_subtree(self):
        root = Path('/qualified/runtime')
        flags = '-DRISC_NATIVE_PACKAGE_VOLUME=1 -DRISC_NATIVE_PROVISION_REQUEST=1 -DRISC_PLATFORM_CAPACITY=32'
        selected = {'file': str(root / 'src/bootstrap/Runtime.cpp'), 'command': 'cc ' + flags}
        library = {'file': str(root / 'lib/elf_loader/src/esp_elf.c'), 'command': 'cc'}
        sibling = {'file': str(root) + '-other/src/Runtime.cpp', 'command': 'cc'}
        escaped = {'file': str(root / 'src/../lib/elf_loader/src/esp_elf.c'), 'command': 'cc'}
        _, rows = provisioning_compile_selection([selected, library, sibling, escaped], root)
        self.assertEqual(rows, [selected])
        relative = dict(selected, file='../src/bootstrap/Runtime.cpp', directory=str(root / 'build'))
        self.assertEqual(provisioning_compile_selection([relative], root)[1], [relative])
        with self.assertRaises(ValueError):
            provisioning_compile_selection([library], root)
        for flag in flags.split():
            missing = dict(selected, command=selected['command'].replace(flag, ''))
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                provisioning_compile_selection([missing, library], root)
            for command in (selected['command'].replace(flag, flag + '0'), selected['command'] + ' ' + flag):
                with self.subTest(command=command), self.assertRaises(ValueError):
                    provisioning_compile_selection([dict(selected, command=command)], root)

    def build(self, root, slots=32, workspace=15208, external=True, debug=True):
        runtime=root/'src/bootstrap/Runtime.cpp';runtime.parent.mkdir(parents=True,exist_ok=True)
        native=root/'src/ports/esp32s3/NativePackageVolume.cpp';native.parent.mkdir(parents=True,exist_ok=True)
        section='__attribute__((section(".ext_ram.bss"),used))' if external else '__attribute__((used))'
        runtime.write_text('namespace RiscBoot { struct Runtime {struct Platform {char bytes[120];}; Platform platforms_['+str(slots)+'];}; Runtime live;}\n'
            'namespace RiscProvisionRequest {namespace { '+section+' static unsigned char bootViewStorage[288];}}\n'
            'namespace RiscCpu {namespace NativeSerialFiles {namespace {'+section+' static unsigned char workspaceStorage[2792];}}}\n'
            'int main(){return RiscBoot::live.platforms_[0].bytes[0];}\n')
        native.write_text('namespace RiscPackageVolume {namespace {struct Workspace {char data['+str(workspace)+'];}; Workspace live;}}\n')
        output=root/'linked';subprocess.run(['c++','-std=c++17','-O0',*(['-g'] if debug else []),str(runtime),str(native),'-o',str(output)],check=True)
        return output.read_bytes()

    def test_complete_linked_type_and_placement(self):
        with tempfile.TemporaryDirectory() as d:
            proof=linked_provisioning_layout(self.build(Path(d)))
        self.assertEqual(proof['types']['platform_slots'],32)
        self.assertEqual(proof['types']['platform_entry_bytes'],120)
        self.assertEqual(proof['types']['package_workspace_bytes'],15208)
        self.assertEqual({v['section'] for v in proof['static_workspaces'].values()},{'.ext_ram.bss'})

    def test_missing_or_changed_native_layout_rejected(self):
        for change in ({'slots':31},{'slots':40},{'workspace':15207},{'external':False},{'debug':False}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                raw=self.build(Path(d),**change)
                with self.assertRaises(ValueError):linked_provisioning_layout(raw)


if __name__=='__main__':unittest.main(verbosity=2)
