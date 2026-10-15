"""Fail-closed effective SDK configuration and compiler argument checks."""
import importlib.util
import hashlib
import os
import subprocess
import json
from pathlib import Path
import re


def require(ok, message):
    if not ok:
        raise ValueError(message)


APP_CONFIG = dict(BOOTLOADER_APP_ROLLBACK_ENABLE=True, ESPTOOLPY_FLASHSIZE_16MB=True,
                  ESPTOOLPY_FLASHMODE_QIO=True, ESPTOOLPY_FLASHFREQ_80M=True,
                  SPIRAM_MODE_OCT=True, SPIRAM_SPEED_80M=True,
                  SPIRAM_ALLOW_BSS_SEG_EXTERNAL_MEMORY=True, SPIRAM_BOOT_INIT=True,
                  STDATOMIC_S32C1I_SPIRAM_WORKAROUND=True, LIBC_NEWLIB=True,
                  ESP_REV_MIN_FULL=0, ESP_REV_MAX_FULL=99)
BOOT_CONFIG = {key: value for key, value in APP_CONFIG.items()
               if not key.startswith(('SPIRAM_', 'STDATOMIC_'))}
FORBIDDEN_CONFIG = ('SECURE_BOOT', 'SECURE_FLASH_ENC_ENABLED', 'BOOTLOADER_APP_ANTI_ROLLBACK')


def header_defines(raw):
    result = {}
    for line in raw.decode().splitlines():
        require(not re.match(r'\s*#undef\s+CONFIG_', line), 'Generated config contains an undef override')
        match = re.fullmatch(r'\s*#define\s+(CONFIG_[A-Z0-9_]+)(?:\s+(.*?))?\s*', line)
        if match:
            require(match[1] not in result, 'Duplicate generated config definition: ' + match[1])
            result[match[1]] = match[2] or ''
    return result


def effective_sdkconfig(blobs):
    """Input config and actual app/bootloader generated configs must agree."""
    inputs = set(blobs['sdkconfig'].decode().splitlines())
    for key, value in APP_CONFIG.items():
        require('CONFIG_' + key + '=' + ('y' if value is True else str(value)) in inputs,
                'Input native SDK configuration differs: ' + key)
    for label, json_key, header_key, required in (
            ('app', 'sdkconfig_json', 'sdkconfig_header', APP_CONFIG),
            ('bootloader', 'bootloader_sdkconfig', 'bootloader_sdkconfig_header', BOOT_CONFIG)):
        actual = json.loads(blobs[json_key])
        header = header_defines(blobs[header_key])
        for key, value in required.items():
            require(type(actual.get(key)) is type(value) and actual[key] == value,
                    'Effective ' + label + ' SDK JSON differs: ' + key)
            require(header.get('CONFIG_' + key) == ('1' if value is True else str(value)),
                    'Effective ' + label + ' SDK header differs: ' + key)
        for key in FORBIDDEN_CONFIG:
            require('CONFIG_' + key + '=y' not in inputs and actual.get(key) in (None, False) and
                    'CONFIG_' + key not in header, 'Unreviewed effective security selection: ' + label + ':' + key)
    return dict(app=APP_CONFIG, bootloader=BOOT_CONFIG, security_selection_unchanged=True)


def compiler_definitions(arguments, required):
    """Respect argument ordering and reject overrides of required selections."""
    defined = {}
    i = 0
    while i < len(arguments):
        token = arguments[i]
        require(not token.startswith('@') and not token.startswith('-Wp,'), 'Unaudited compiler response/preprocessor arguments')
        operation = None
        if token in ('-D', '-U'):
            operation = token
            i += 1
            require(i < len(arguments), 'Missing compiler macro argument')
            expression = arguments[i]
        elif token.startswith(('-D', '-U')):
            operation, expression = token[:2], token[2:]
        if operation:
            name, separator, value = expression.partition('=')
            require(bool(name), 'Empty compiler macro name')
            if operation == '-U':
                require(name not in required, 'Required compiler definition undefined: ' + name)
                defined.pop(name, None)
            else:
                value = value if separator else '1'
                if name in required:
                    require(value == required[name], 'Required compiler definition overridden: ' + name)
                require(name not in defined or defined[name] == value, 'Conflicting compiler definitions: ' + name)
                defined[name] = value
        i += 1
    require(all(defined.get(key) == value for key, value in required.items()), 'Missing effective compiler profile definition')
    return defined


def local_module(root, filename, name):
    """Do not let an image-helper checkout shadow product qualification code."""
    path = Path(root) / 'scripts' / filename
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'Missing product-local qualification module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(Path(module.__file__).resolve() == path.resolve(), 'Product-local module resolution differs')
    return module


def expand_response_files(arguments, build, directory, blobs, artifact_rows):
    """IDF6 uses generated toolchain response files; consume only locked bytes."""
    import shlex
    root = Path(build).resolve()
    allowed = {str((root / row['path']).resolve()): blobs[key] for key, row in artifact_rows.items()
               if key.startswith(('response_', 'boot_response_'))}
    def expand(tokens, ancestors=()):
        result = []
        for token in tokens:
            if not token.startswith('@'):
                result.append(token)
                continue
            path = Path(token[1:])
            path = (Path(directory) / path).resolve() if not path.is_absolute() else path.resolve()
            require(str(path) in allowed and str(path) not in ancestors, 'Unpinned/cyclic compiler response file: ' + str(path))
            result.extend(expand(shlex.split(allowed[str(path)].decode()), (*ancestors, str(path))))
        return result
    return expand(arguments)


COMPILER_FAMILY_NAMES = {'gcc': 'xtensa-esp-elf-gcc', 'g++': 'xtensa-esp-elf-g++',
                         's3-gcc': 'xtensa-esp32s3-elf-gcc', 's3-g++': 'xtensa-esp32s3-elf-g++'}


def compiler_family(compiler):
    """Pin the generic drivers, official S3 wrappers and their dynamic config."""
    compiler = Path(compiler).resolve()
    require(compiler.name == 'xtensa-esp-elf-gcc', 'Pinned generic native GCC driver required')
    paths = {name: compiler.with_name(filename) for name, filename in COMPILER_FAMILY_NAMES.items()}
    paths['xtensa-config'] = compiler.parent.parent / 'lib/xtensa_esp32s3.so'
    result = {}
    for role, path in paths.items():
        require(path.is_file() and path.resolve().is_relative_to(compiler.parent.parent), 'Compiler family member missing/escaped: ' + role)
        raw = path.read_bytes()
        result[role] = {'path': str(path.resolve()), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    env = {key: value for key, value in os.environ.items() if not key.startswith('XTENSA_') and key not in
           ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH')}
    for role in COMPILER_FAMILY_NAMES:
        path = paths[role]
        version = subprocess.check_output([str(path), '--version'], env=env, text=True).splitlines()[0]
        require('15.2.0' in version and 'esp-15.2.0_20251204' in version, 'Unreviewed native compiler family version: ' + role)
        require(subprocess.check_output([str(path), '-dumpmachine'], env=env, text=True).strip() == 'xtensa-esp-elf', 'Wrong compiler target: ' + role)
        flags = [] if role.startswith('s3-') else ['-mdynconfig=xtensa_esp32s3.so']
        require(subprocess.check_output([str(path), *flags, '-print-multi-directory'], env=env, text=True).strip() == 'esp32s3', 'Wrong compiler Xtensa configuration: ' + role)
    return result


def compiler_command(arguments, compiler, family):
    """Accept exact pinned executables and reject configuration/tool overrides."""
    require(arguments, 'Empty compiler invocation')
    compiler = Path(compiler).resolve()
    invoked = Path(arguments[0])
    require(invoked.is_absolute() and invoked.parent.resolve() == compiler.parent, 'Compiler command is outside pinned tool directory')
    role = next((role for role, filename in COMPILER_FAMILY_NAMES.items() if invoked.name == filename), None)
    require(role is not None and str(invoked.resolve()) == family[role]['path'], 'Compiler command is not a pinned native family member')
    config = []
    for argument in arguments[1:]:
        require(not argument.startswith(('-B', '-specs', '--specs', '-wrapper', '--sysroot', '-isysroot', '-fplugin', '-iplugindir')),
                'Compiler child-tool/specification override')
        if argument.startswith('-mdynconfig='):
            config.append(argument.split('=', 1)[1])
        elif 'dynconfig' in argument or argument.startswith('@'):
            raise ValueError('Unreviewed Xtensa configuration or unexpanded response override')
    if role.startswith('s3-'):
        require(not config, 'Official S3 wrapper configuration overridden')
    else:
        require(config == ['xtensa_esp32s3.so'], 'Generic compiler requires exactly one explicit S3 configuration')
    return role
