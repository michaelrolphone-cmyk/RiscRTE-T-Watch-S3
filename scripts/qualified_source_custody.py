"""Bind non-system compiler inputs to pinned Git blobs before running a harness.

Use the compiler's own dependency search, including ignored/untracked headers.
System headers and the compiler are the host toolchain, not product source.
"""
from pathlib import Path
import os
import shlex
import subprocess


def source_head(root, expected=None):
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if expected is not None and head != expected:
        raise ValueError('Compiler source revision differs: ' + str(root))
    return head


def dependency_command(command):
    """Preserve preprocessing options while removing output/link-only inputs."""
    # GCC otherwise omits a consumed .gch and can report the original .h while
    # normal compilation silently uses different precompiled definitions.
    result = [str(command[0]), '-MM', '-fpch-preprocess', '-MT', 'qualified-inputs']
    skip = False
    for value in map(str, command[1:]):
        if skip:
            skip = False
            continue
        if value == '-o':
            skip = True
        elif value == '-c' or value.startswith(('-Wl,', '-l')) or value.endswith('.o'):
            continue
        else:
            result.append(value)
    return result


def dependencies(command, timeout):
    output = subprocess.check_output(dependency_command(command), text=True, timeout=timeout)
    result = set()
    for rule in output.replace('\\\n', ' ').splitlines():
        if rule.startswith('#pragma GCC pch_preprocess'):
            raise ValueError('Precompiled compiler input is not qualified: ' + rule)
        if not rule.startswith('qualified-inputs:'):
            raise ValueError('Unexpected compiler dependency output')
        for name in shlex.split(rule.split(':', 1)[1]):
            path = Path(os.path.abspath(name))
            if Path(name).resolve() != path:
                raise ValueError('Linked compiler input: ' + name)
            result.add(path)
    if not result:
        raise ValueError('Compiler dependency closure is empty')
    return result


def ordinary_file(path, root):
    relative = path.relative_to(root)
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError('Linked compiler input: ' + str(path))
    if not path.is_file():
        raise ValueError('Missing compiler input: ' + str(path))
    return path.read_bytes()


def run_qualified(command, *, sources, generated=None, timeout=180):
    """Compile only qualified inputs; repeat custody checks before returning.

    sources maps repository roots to independently selected commit IDs. Exact
    generated headers/objects belong to a fresh build directory and are the
    only allowed non-system dependencies outside those repositories.
    """
    sources = {Path(root).resolve(): revision for root, revision in sources.items()}
    generated = {Path(path).absolute(): data for path, data in (generated or {}).items()}
    for root, revision in sources.items():
        source_head(root, revision)

    def check():
        for path, expected in generated.items():
            if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
                raise ValueError('Generated compiler input changed: ' + str(path))
        paths = dependencies(command, timeout)
        qualified = {}
        for path in paths:
            if path in generated:
                qualified[path] = generated[path]
                continue
            root = next((root for root in sources if path.is_relative_to(root)), None)
            if root is None:
                raise ValueError('Compiler input outside pinned sources: ' + str(path))
            relative = path.relative_to(root).as_posix()
            try:
                expected = subprocess.check_output(
                    ['git', '-C', str(root), 'show', sources[root] + ':' + relative], stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as error:
                raise ValueError('Compiler input is not in pinned source: ' + str(path)) from error
            actual = ordinary_file(path, root)
            if actual != expected:
                raise ValueError('Compiler input differs from pinned source: ' + str(path))
            qualified[path] = actual
        for root, revision in sources.items():
            source_head(root, revision)
        return qualified

    before = check()
    subprocess.run(list(map(str, command)), check=True, timeout=timeout)
    if check() != before:
        raise ValueError('Compiler dependency closure changed during compilation')
