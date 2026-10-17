"""Production-source store admission and offline inactive-bank fault models.

These models never execute Xtensa instructions or operate a physical device.
They do not establish compatibility of an SDK6 app with a deployed bootloader.
"""
import contextlib
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(text, old, new):
    require(text.count(old) == 1, 'Admission fixture source anchor changed: ' + old)
    return text.replace(old, new, 1)


def wave_fixture(source, product, sdk):
    from verify_update_elf import extract
    source = '#include "experimental/native_replica/NativeAtomicKeyValue.h"\n' + source
    source = replace_once(source, 'bool bind(RiscBoot::Runtime& runtime) {', '''using RC=RiscExperimental::NativeReplicaCore;
using AE=RiscExperimental::NativeAtomicKeyValue;
static RC core1(1,{}, {}, {}),core6(6,{}, {}, {});
static AE endpoint1(core1,{nullptr,[](void*){return true;},[](void*){++storageCalls;return false;},[](void*){++storageCalls;return false;},[](void*){++storageCalls;return false;},[](void*){++storageCalls;return -1;}});
static AE endpoint6(core6,{nullptr,[](void*){return true;},[](void*){++storageCalls;return false;},[](void*){++storageCalls;return false;},[](void*){++storageCalls;return false;},[](void*){++storageCalls;return -1;}});
bool bind(RiscBoot::Runtime& runtime) {
 struct Writer {const char* app;uint32_t ns;};
 static const Writer writers[]={RISC_NATIVE_SETTINGS_WRITERS};
 for(const auto& writer:writers)if(!runtime.registerAtomicKeyValue(writer.app,writer.ns,writer.ns==6?endpoint6:endpoint1))return false;
 for(uint32_t ns:{1u,6u})if(!runtime.registerAtomicKeyValueReadThrough(ns,ns==6?endpoint6:endpoint1)||!runtime.registerKeyValueAvailability(ns,{nullptr,[](void*,uint32_t,risc_key_value_availability_state_v1*)->int32_t{++storageCalls;return RISC_KEY_VALUE_IO;}}))return false;
''')
    vendor = (product / 'native/VendorDisplayIdf6.inc').read_text()
    constants = re.search(r'^constexpr uint16_t Width=[^\n]+;', vendor, re.M)
    require(constants is not None, 'Native CO5300 dimensions source missing')
    # The target predicate is extracted unchanged; the SDK's S3 valid-output
    # mask is the same constant consumed by GPIO_IS_VALID_OUTPUT_GPIO.
    caps = (sdk / 'components/soc/esp32s3/include/soc/soc_caps.h').read_text()
    mask = re.search(r'^#define SOC_GPIO_VALID_GPIO_MASK\s+([^\n]+)', caps, re.M)
    require(mask is not None, 'Pinned S3 GPIO capability mask missing')
    mask_expression = mask.group(1).strip()
    require(mask_expression == '(0x1FFFFFFFFFFFFULL & ~(0ULL | BIT22 | BIT23 | BIT24 | BIT25))', 'Unreviewed SDK S3 GPIO mask')
    mask_expression = re.sub(r'BIT(\d+)', lambda m: '(UINT64_C(1)<<' + m.group(1) + ')', mask_expression)
    predicate = constants.group() + '\n' + '#define GPIO_IS_VALID_OUTPUT_GPIO(pin) ((pin)>=0 && (pin)<49 && ((' + mask_expression + ') & (UINT64_C(1)<<(pin))))\n' + extract(vendor, 'bool accepts(') + '\n#undef GPIO_IS_VALID_OUTPUT_GPIO\n'
    source = replace_once(source, 'RiscCpu::Hardware hardware() {', predicate + '\nRiscCpu::Hardware hardware() {')
    source = replace_once(source, '  RiscCpu::Hardware h{};', '''  RiscCpu::Hardware h{};
 static RiscCpu::DisplayBackend display{accepts,[](const risc_hardware_device_v1&,uint8_t){++hardwareCalls;return false;},[](uint32_t,const uint16_t*,size_t){++hardwareCalls;return false;},[](uint8_t){++hardwareCalls;return false;},[](){++hardwareCalls;return false;}};
 h.displayBackend=&display;
 h.i2sStandardOpen=[](const risc_hw_i2s_standard_v1&,uint8_t,uint32_t){++hardwareCalls;return false;};
 static RiscStorage::Worker mailbox;
 static RiscCpu::StorageWorkBackend worker{&mailbox,[](){return true;},[](){return false;},[](uint32_t){++hardwareCalls;}};h.storageWork=&worker;
 h.sdmmcOpen=[](uint8_t,uint8_t,uint8_t,uint32_t,risc_sdmmc_card_info_v1*){++hardwareCalls;return false;};
 h.sdmmcRead=[](uint64_t,uint32_t,void*){++hardwareCalls;return false;};h.sdmmcWrite=[](uint64_t,uint32_t,const void*){++hardwareCalls;return false;};h.sdmmcSync=[](){++hardwareCalls;return false;};h.sdmmcClose=[](){++hardwareCalls;return false;};
''')
    return source


def source_bound_header(generated):
    # Extract the exact generated body shape rather than replacing the
    # production admission function or its compiled public export table.
    anchor = 'static bool file(void* context,const char* path,bool provider){'
    require(generated.count(anchor) == 1, 'Admission image callback source anchor changed')
    start = generated.index(anchor)
    end = generated.index('\n}', start) + 2
    replacement = """struct Context { RiscBoot::Runtime* candidate; unsigned admitted; };
static bool file(void* context,const char* path,bool provider){
 auto& c=*static_cast<Context*>(context);
 RiscBoot::RuntimeFileImage image;
 if(!image.read(c.candidate->imageSource(),path,{malloc,free,
     [](void*){return operationSafe();},[](void*,size_t){vTaskDelay(1);return operationSafe();},nullptr}))return false;
 const bool valid=admitElf(image.bytes,image.size,provider?ElfRole::Driver:ElfRole::Application);
 free(image.bytes);if(!valid)return false;++c.admitted;return true;
}"""
    generated = generated[:start] + replacement + generated[end:]
    return '#include "bootstrap/RuntimeFileImage.h"\n' + generated


def source_bound_fixture(source, runtime):
    source = replace_once(source, '#undef private', '#undef private\n#include "' + str(runtime / 'test/RuntimeFileFixture.h') + '"')
    source = replace_once(source, '  RiscBoot::Runtime runtime(runtimePort);',
        '  RiscTest::FileSources files({std::string(argv[1]),std::string(argv[2])},owner,owner);\n'
        '  runtimePort.files=files.sources();\n  RiscBoot::Runtime runtime(runtimePort);')
    source = replace_once(source, 'RiscBoot::Runtime candidate({});unsigned admitted=0;',
        'RiscBoot::Runtime candidate({});CohortElf::Context admitted{&candidate,0};')
    source = replace_once(source, 'storageCalls,admitted,cooperativeYields);',
        'storageCalls,admitted.admitted,cooperativeYields);')
    return source


def admit_product(sources, native, before, after, native_proof, sanitized=False):
    import check_runtime_store_admission as admission
    import verify_update_elf as verify
    runtime, product, helper = (sources[n] for n in ('runtime', 'product', 'image_helper'))
    contract = json.loads((product / 'docs/native-idf61/released-baseline.json').read_bytes())
    old_root, old_composition, old_header = admission.ROOT, admission.native_composition, verify.cohort_admission_header
    old_run, old_sanitize = subprocess.run, os.environ.get('SANITIZE')
    commands = []
    def composition(selected_runtime, elf, profile, rows):
        require(Path(selected_runtime) == runtime and elf == native and rows == 32 and
                Path(profile) == product / 'profiles/native-idf61.cmake', 'Wrong native host composition')
        return dict(bounds={'RISC_INSTALLED_APP_CAPACITY': 64, 'RISC_PROVIDER_CAPACITY': 40,
                            'RISC_APP_POLICY_ROWS': 32, 'RISC_APP_REQUIREMENT_ROWS': 32},
                    store_abi=3, file_source_enabled=True, runtime_commit=run_head(runtime),
                    native_layout=native_proof['native_layout'], product_profile_sha256=sha(Path(profile).read_bytes()))
    def header(*args, **kwargs):
        generated = old_header(*args, **kwargs)
        if 'RiscPlatform::millis()' in generated:
            generated = replace_once(generated, 'static uint32_t millis(){return ticks;}',
                                     'namespace RiscPlatform { static uint32_t millis(){return ticks;} }')
        return source_bound_header(generated)
    def run(command, *args, **kwargs):
        if isinstance(command, list) and command and command[0] in ('c++', 'cc'):
            command = [command[0], '-DRISC_NATIVE_ESP_IDF=1', *command[1:]]
            if command[0] == 'c++' and contract['product'] == 'waveshare':
                command = [command[0], '-DRISC_RUNTIME_ATOMIC_KEY_VALUE=1', '-include',
                           str(product / 'profiles/native-idf61-settings.h'), '-I' + str(runtime), '-I' + str(runtime / 'test/native_nvs_shim'),
                           '-Wno-unused-function', '-Wno-unused-but-set-variable', *command[1:]]
            commands.append([str(x) for x in command])
        return old_run(command, *args, **kwargs)
    try:
        os.environ['SANITIZE'] = '1' if sanitized else '0'
        os.environ.setdefault('ASAN_OPTIONS', 'detect_leaks=0')
        admission.native_composition, verify.cohort_admission_header, subprocess.run = composition, header, run
        with tempfile.TemporaryDirectory(prefix='native-idf61-admission-') as tmp:
            root = Path(tmp)
            (root / 'tests').mkdir()
            source = (helper / 'tests/runtime_store_admission.cpp').read_text()
            source = source_bound_fixture(source, runtime)
            if contract['product'] == 'waveshare':
                source = wave_fixture(source, product, sources['sdk'])
            (root / 'tests/runtime_store_admission.cpp').write_text(source)
            shutil.copyfile(helper / 'tests/app_data_admission_backend.h', root / 'tests/app_data_admission_backend.h')
            admission.ROOT = root
            result = admission.admit_cohort(runtime, native, before, after, app_policy_rows=32,
                                            native_profile=product / 'profiles/native-idf61.cmake')
            result.update(sanitized=sanitized, fixture_sha256=sha(source.encode()),
                          hardware_calls=0, storage_calls=0, target_instructions_executed=False)
            require(result['elf_count'] == contract['elf_count'], 'Released ELF inventory not completely admitted')
            return result
    finally:
        admission.ROOT, admission.native_composition, verify.cohort_admission_header = old_root, old_composition, old_header
        subprocess.run = old_run
        if old_sanitize is None:
            os.environ.pop('SANITIZE', None)
        else:
            os.environ['SANITIZE'] = old_sanitize


def run_head(root):
    return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()


def preservation_model(baseline, candidate, digest):
    from prepare_preserving_update import layout, pair, plan, selection, ota
    from paired_bank_images import record
    geometry = layout(baseline)
    expanded, natives, stores, size = geometry
    require(expanded and size == 0x550000, 'Wrong preservation layout')
    _, old_fw, old_store = pair(baseline, 0, geometry)
    _, firmware, store = pair(candidate, 0, geometry)
    cases = []
    def active(image):
        rows = [row for i in range(2) if (row := ota(image[0xff0000+i*4096:0xff0020+i*4096]))]
        return (max(rows)[0] - 1) % 2
    def protected(before, after, ranges):
        require(all(before[start:end] == after[start:end] for start, end in ranges), 'Protected preservation range changed')
    def rejected(snapshot, target=candidate, baseline_digest=digest):
        try:
            plan(snapshot, baseline, target, baseline_digest)
        except ValueError:
            return
        raise ValueError('Unsafe preserving plan accepted')
    for bank in (0, 1):
        for sector in (0, 1):
            for both_valid in (False, True):
                snapshot = bytearray(baseline)
                snapshot[natives[bank]:natives[bank]+len(old_fw)] = old_fw
                snapshot[stores[bank]:stores[bank]+size] = old_store
                snapshot[0xff2000+bank*4096:0xff3000+bank*4096] = record(bank, old_fw, old_store, True, True) + b'\xff'*(4096-96)
                sequence = bank + 3
                offset = 0xff0000 + sector*4096
                snapshot[0xff0000:0xff2000] = b'\xff'*8192
                snapshot[offset:offset+4096] = selection(sequence, 2)
                if both_valid:
                    older = 0xff0000 + (1-sector)*4096
                    snapshot[older:older+4096] = selection(sequence-1, 2)
                snapshot[0x9000:0xf000] = bytes(range(256))*96
                snapshot[0x270000:0x2f0000] = bytes(reversed(range(256)))*2048
                rows, receipt = plan(snapshot, baseline, candidate, digest)
                require([row[0] for row in rows] == ['firmware.bin', 'store.bin', 'bank-state.bin', 'ota-selection-LAST.bin'], 'Selection must be last')
                require(receipt['target_bank'] == 1-bank, 'Active bank would be overwritten')
                for index in range(3):
                    name, at, data = rows[index]
                    for cut in (0, 1, len(data)//2, len(data)-1, len(data)):
                        partial = bytearray(snapshot)
                        for _, previous, payload in rows[:index]:
                            partial[previous:previous+len(payload)] = payload
                        erased = (len(data)+4095)//4096*4096
                        partial[at:at+erased] = b'\xff'*erased
                        partial[at:at+cut] = data[:cut]
                        protected(snapshot, partial, receipt['preserved_ranges'])
                        require(active(partial) == bank, 'Torn payload changed active selector')
                        pair(partial, bank, geometry)
                        cases.append('inactive-payload-torn')
                ready = bytearray(snapshot)
                for _, at, data in rows[:3]:
                    ready[at:at+len(data)] = data
                _, at, data = rows[-1]
                for cut in range(33):
                    partial = bytearray(ready)
                    partial[at:at+4096] = b'\xff'*4096
                    partial[at:at+cut] = data[:cut]
                    protected(snapshot, partial, receipt['preserved_ranges'])
                    selected = active(partial)
                    require(selected == (1-bank if cut == 32 else bank), 'Torn selection changed prior to complete CRC record')
                    pair(partial, selected, geometry)
                    cases.append('selection-torn')
                for fault in ('active-native', 'active-store', 'active-state', 'not-confirmed', 'equal-sequence', 'sequence-limit', 'bootloader', 'partition', 'digest'):
                    bad = bytearray(snapshot)
                    at = {'active-native': natives[bank], 'active-store': stores[bank], 'active-state': 0xff2000+bank*4096,
                          'bootloader': 0, 'partition': 0x8000}.get(fault)
                    if at is not None:
                        bad[at] ^= 1
                    elif fault == 'not-confirmed':
                        bad[offset:offset+4096] = selection(sequence, 0)
                    elif fault == 'equal-sequence':
                        bad[0xff0000:0xff2000] = selection(sequence, 2)*2
                    elif fault == 'sequence-limit':
                        bad[offset:offset+4096] = selection(0xfffffffe, 2)
                    rejected(bad, baseline_digest='0'*64 if fault == 'digest' else digest)
                    cases.append('rejected-' + fault)
                for at in (0, 0x8000, 0x10000, 0x2f0000, 0xff2000):
                    bad = bytearray(candidate)
                    bad[at] ^= 1
                    rejected(snapshot, target=bad)
                    cases.append('candidate-corruption')
                ready[rows[-1][1]:rows[-1][1]+len(rows[-1][2])] = rows[-1][2]
                protected(snapshot, ready, receipt['preserved_ranges'])
                require(pair(ready, 1-bank, geometry)[1:] == (firmware, store), 'Selected native/store pair differs')
    return dict(passed=True, cases=len(cases), both_active_banks=True, both_selector_sectors=True,
                fresh_exact_baseline_readback_required=True, nvs_and_appdata_preserved=True,
                separate_selection_written_last=True, target_instructions_executed=False,
                bootloader_compatibility_tested=False, hardware_tested=False)
