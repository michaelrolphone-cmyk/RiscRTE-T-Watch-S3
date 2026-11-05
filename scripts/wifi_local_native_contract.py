"""Fail-closed selection and additive-source contract for Watch qualification."""
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDITIONS = {
    '.github/workflows/wifi-local-native.yml',
    'docs/wifi-local-native/README.md',
    'docs/wifi-local-native/source-pins.json',
    'profiles/wifi-local-native-qualification.cmake',
    'profiles/wifi-local-native-qualification.h',
    'scripts/build_wifi_local_native.py',
    'scripts/test_wifi_local_native.py',
    'scripts/wifi_local_native_contract.py',
    'tests/wifi_local_native/layout.cpp',
}
EXTRA = {
    'RISC_NATIVE_SETTINGS_PORT_SELECTED': '1',
    'RISC_NATIVE_SETTINGS_LIFECYCLE': '1',
    'RISC_NATIVE_SETTINGS_WORKER': '1',
    'RISC_RUNTIME_ATOMIC_KEY_VALUE': '1',
    'RISC_NATIVE_STORAGE_CUSTODY': '1',
    'RISC_NATIVE_SETTINGS_BACKEND': '1',
    'RISC_NATIVE_SETTINGS_ASSEMBLY': '1',
    'RISC_NATIVE_SETTINGS_PSRAM_PAYLOAD': '1',
    'RISC_NATIVE_SETTINGS_LOCAL_ONLY': '1',
    'RISC_NATIVE_SETTINGS_LOCAL_FRESH': '0',
    'RISC_NATIVE_SETTINGS_VOLUME_INSTANCE': '0',
    'RISC_NATIVE_SETTINGS_NAMESPACE_MASK': '2',
}
FIELDS = {
    'definitions': 'RISC_NATIVE_DEFINITIONS', 'target': 'RISC_NATIVE_TARGET',
    'partitions': 'RISC_NATIVE_PARTITIONS', 'settings': 'RISC_NATIVE_SETTINGS_HEADER',
    'extra': 'RISC_NATIVE_EXTRA_SOURCES', 'appdata': 'RISC_NATIVE_APPDATA',
    'iq': 'RISC_NATIVE_IQ', 'link': 'RISC_NATIVE_LINK_OPTIONS',
    'options': 'RISC_NATIVE_COMPILE_OPTIONS', 'includes': 'RISC_NATIVE_INCLUDE_DIRECTORIES',
}

def require(ok, message):
    if not ok:
        raise ValueError(message)

# These allocated symbols have mixed C representations in the pinned Runtime.
# PairedBank is a NUL-terminated marker, while backend/capacity markers are u32.
LINKED_MARKERS = {
    'risc_paired_store_abi': b'RISC_PAIRED_STORE_ABI:3\0',
    'risc_tcp_listener_abi': (1).to_bytes(4, 'little'),
    'risc_entropy_abi': (1).to_bytes(4, 'little'),
    'risc_file_source_abi': (1).to_bytes(4, 'little'),
    'risc_installed_app_capacity': (64).to_bytes(4, 'little'),
    'risc_app_policy_rows': b'RISC_APP_POLICY_ROWS:32\0',
    'risc_app_requirement_rows': b'RISC_APP_REQUIREMENT_ROWS:32\0',
}

def validate_linked_markers(actual):
    require(set(actual) == set(LINKED_MARKERS), 'Missing or unexpected linked ABI marker')
    for name, expected in LINKED_MARKERS.items():
        require(actual[name] == expected, 'Released linked ABI changed: ' + name)

def pins():
    p = json.loads((ROOT / 'docs/wifi-local-native/source-pins.json').read_bytes())
    require(type(p['schema']) is int and p['schema'] == 1 and p['publication_enabled'] is False
            and p['product_activation_enabled'] is False and p['hardware_tested'] is False,
            'Qualification boundary changed')
    require(p['product_base_revision'] == '81dbde86969615f7378cc03c5800960a9092e076'
            and p['sdk_revision'] == 'fff9895c82d744c7237be8847347bdd1b07c6643'
            and p['partition_blob'] == 'b7f916aa0261e0723fe0f5eb75977a847c67290e',
            'Released source/SDK/partition anchor changed')
    require(re.fullmatch('[0-9a-f]{40}', p['runtime_revision']) and
            re.fullmatch(r'\d+\.\d+\.\d+', p['runtime_version']), 'Exact Runtime source/version required')
    require(p['baseline_profile'] == 'profiles/native-provisioning.cmake'
            and p['qualification_profile'] == 'profiles/wifi-local-native-qualification.cmake',
            'Qualification profile paths changed')
    return p

def definitions(text):
    result = {}
    for row in text.split(';'):
        if not row:
            continue
        name, separator, value = row.partition('=')
        require(separator and name not in result, 'Missing or duplicate definition: ' + row)
        result[name] = value
    return result

def validate_source_rows(rows):
    require(set(rows) == {'A\t' + path for path in ADDITIONS} and len(rows) == len(ADDITIONS),
            'Candidate must add exactly its isolated files; existing source is immutable')

def source_guard():
    p = pins()
    raw = subprocess.check_output(['git', '-C', str(ROOT), 'diff', '--no-renames',
                                   '--name-status', p['product_base_revision'], 'HEAD'], text=True)
    validate_source_rows(raw.splitlines())
    require(not subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain']).strip(),
            'Qualification checkout is dirty')

def cmake_script(runtime, profile, output):
    # Keep the dollar and opening brace separate in this Python generator.
    fields = ''.join(key + '=$' + '{' + variable + '}\\n' for key, variable in FIELDS.items())
    return ('set(RISC_RUNTIME_ROOT "' + str(runtime) + '")\n'
            'include("' + str(ROOT / profile) + '")\n'
            'file(WRITE "' + str(output) + '" "' + fields + '")\n')

def expanded(runtime, profile, cmake='cmake'):
    with tempfile.TemporaryDirectory(prefix='watch-wifi-profile-') as tmp:
        output = Path(tmp) / 'selection.txt'
        script = Path(tmp) / 'selection.cmake'
        script.write_text(cmake_script(runtime, profile, output))
        subprocess.run([str(cmake), '-P', str(script)], check=True)
        return dict(line.split('=', 1) for line in output.read_text().splitlines())

def validate_delta(before, after):
    old, new = definitions(before['definitions']), definitions(after['definitions'])
    require(not set(old) & set(EXTRA), 'Released baseline already selects lifecycle policy')
    require(new == {**old, **EXTRA}, 'Only the explicit local Wi-Fi settings definitions may be added')
    require(old['RISC_PROVIDER_CAPACITY'] == '40' and old['RISC_PLATFORM_CAPACITY'] == '32'
            and old['RISC_INSTALLED_APP_CAPACITY'] == '64'
            and old['RISC_APP_POLICY_ROWS'] == old['RISC_APP_REQUIREMENT_ROWS'] == '32',
            'Released resource capacities changed')
    require(before['settings'] == '' and after['settings'] ==
            str(ROOT / 'profiles/wifi-local-native-qualification.h'), 'Settings header selection differs')
    require(before['options'] == '' and after['options'] == '-fstack-usage',
            'Only compiler frame diagnostics may be added')
    require({k: v for k, v in before.items() if k not in ('definitions', 'settings', 'options')} ==
            {k: v for k, v in after.items() if k not in ('definitions', 'settings', 'options')},
            'Physical, storage, SDK, link or provider selection changed')
    require(before['appdata'] == before['iq'] == 'ON', 'Released AppData/IQ selection changed')

def profile_contract(runtime, cmake='cmake'):
    p = pins()
    before, after = [expanded(runtime, p[key], cmake)
                     for key in ('baseline_profile', 'qualification_profile')]
    validate_delta(before, after)
    partition = Path(after['partitions']).read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(partition)).encode() + b'\0' + partition).hexdigest()
    require(blob == p['partition_blob'], 'Historical/current expanded partition source differs')
    header = (ROOT / 'profiles/wifi-local-native-qualification.h').read_text()
    require('#define RISC_NATIVE_SETTINGS_WRITERS {"wifi_settings",6}' in header,
            'Wi-Fi writer identity changed')
    return before, after
