"""Explicit product serial admission; no device, timing or durability claims."""
import io
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def contract(product):
    require(product in ('twatch', 'waveshare'), 'Unknown serial product')
    flags = {'RISC_NATIVE_SERIAL_FILES': 1, 'RISC_NATIVE_SERIAL_APPDATA_FILES': 1}
    namespaces = [{'id': 2, 'label': 'Serial files', 'writable': True,
                   'private_root': '/appdata/.serial-files'}]
    if product == 'waveshare':
        flags['RISC_NATIVE_SERIAL_SD'] = 1
        namespaces.append({'id': 12, 'label': 'SD card', 'writable': True,
                           'backend_provider': 'sdmmc-fatfs', 'backend_instance': 12})
    return {'flags': flags, 'namespaces': namespaces, 'boot_export_enabled': False,
            'active_boot_bank_writable': False, 'application_grants_reused': False,
            'dispatch': 'settled-owner-checkpoint', 'hardware_tested': False}


def check_profile(text, product, previous=None):
    selected = re.search(r'set\(RISC_NATIVE_DEFINITIONS\s+(.*?)\)', text, re.S)
    require(selected is not None, 'Missing native definitions')
    definitions = re.findall(r'\b(RISC_[A-Z0-9_]+)=(\d+)\b', selected.group(1))
    require(len({k for k, _ in definitions}) == len(definitions), 'Duplicate native definition')
    flags = {k: int(v) for k, v in definitions if k.startswith('RISC_NATIVE_SERIAL_')}
    expected = contract(product)
    require(flags == expected['flags'], 'Unexpected serial namespace selection')
    all_flags = dict(definitions)
    for flag in ('RISC_RUNTIME_STORAGE_FILES', 'RISC_PAIRED_APP_DATA', 'RISC_NATIVE_APP_DATA_MOUNT'):
        require(all_flags.get(flag) == '1', 'Serial private storage prerequisite missing: ' + flag)
    if product == 'waveshare':
        require(all_flags.get('RISC_ENABLE_SDMMC') == '1', 'Serial SD provider prerequisite missing')
    if previous is not None:
        stripped = ''.join(line for line in text.splitlines(keepends=True)
                           if not re.fullmatch(r'\s*RISC_NATIVE_SERIAL_[A-Z_]+=\d+\s*', line))
        require(stripped == previous, 'Unrelated native product profile input changed')
    return expected


RUNTIME_SOURCES = ('src/runtime/serial/Files.cpp', 'src/runtime/storage/ReopenedFiles.cpp',
                   'src/ports/esp32s3/NativeSerialFiles.cpp', 'src/ports/esp32s3/NativeSerialStorage.cpp')


def linked_symbols(raw):
    from elftools.elf.elffile import ELFFile
    elf = ELFFile(io.BytesIO(raw))
    return [s.name for s in elf.get_section_by_name('.symtab').iter_symbols()
            if s['st_shndx'] != 'SHN_UNDEF']


def check_native(blobs, native_proof, product, runtime, profile):
    import hashlib
    expected = check_profile(profile, product)
    for path in RUNTIME_SOURCES:
        digest = hashlib.sha256((runtime / path).read_bytes()).hexdigest()
        require(native_proof['source_files'].get('runtime/' + path) == digest,
                'Exact serial implementation was not compiled: ' + path)
    names = linked_symbols(blobs['firmware_elf'])
    for fragment in ('NativeSerialStorage', 'NativeSerialFiles', 'ReopenedFiles'):
        require(any(fragment in name for name in names), 'Serial implementation was not linked: ' + fragment)
    require(b'/appdata/.serial-files\0' in blobs['firmware_bin'], 'Private serial root absent from native firmware')
    if product == 'waveshare':
        require(any('NativeSerialStorage' in name and 'sdFiles' in name for name in names), 'Separate serial SD client absent')
    return expected
