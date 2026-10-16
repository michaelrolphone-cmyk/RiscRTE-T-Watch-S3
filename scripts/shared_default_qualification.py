"""Shared-default production admission with explicit optional storage brokers.

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
 for(const auto& writer:writers)if((writer.ns!=1 && writer.ns!=6)||!runtime.registerAtomicKeyValue(writer.app,writer.ns,writer.ns==6?endpoint6:endpoint1))return false;
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
        # Extract the exact generated body shape rather than replacing the
        # production admission function or its compiled public export table.
        start = generated.index('static bool file(void* context,const char* path,bool provider){')
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
    def run(command, *args, **kwargs):
        if isinstance(command, list) and command and command[0] in ('c++', 'cc'):
            command = [command[0], '-DRISC_NATIVE_ESP_IDF=1', '-DRISC_RUNTIME_PREFERENCE_STORE=1', '-DRISC_RUNTIME_STORAGE_FILES=1', *command[1:]]
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
            source = replace_once(source, '#undef private', '#undef private\n#include "' + str(runtime / 'test/RuntimeFileFixture.h') + '"')
            source = replace_once(source, '  RiscBoot::Runtime runtime(runtimePort);',
                '  RiscTest::FileSources files({std::string(argv[1]),std::string(argv[2])},owner,owner);\n'
                '  runtimePort.files=files.sources();\n  RiscBoot::Runtime runtime(runtimePort);')
            source = replace_once(source, 'RiscBoot::Runtime candidate({});unsigned admitted=0;',
                'RiscBoot::Runtime candidate({});CohortElf::Context admitted{&candidate,0};')
            source = replace_once(source, 'storageCalls,admitted,cooperativeYields);',
                'storageCalls,admitted.admitted,cooperativeYields);')
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

