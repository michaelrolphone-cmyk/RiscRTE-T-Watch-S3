#!/usr/bin/env python3
"""Compile real retained Settings sources with every recorded feature flag.

Host compiler/linker replaces target Xtensa-only options. This does not rebuild,
execute, or attest instruction identity of the retained Settings ELF.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

PINS = {"producer_system": "9dcb2bbef44853e533d980a658a814d2c787a4fa", "bridge": "6e82fdcaec0b73ed700d2104cfb4d94f011c19d4", "product": "ab9ff33975680c5bb8d9a2e7ed346d0300732a4e"}
RECIPE_SHA256 = "20744e0d0db102dab810ae3cb243e0657c2fab9ba738959ca742024c6f3a6ed0"

def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args])

def verify(path, expected):
    actual = git(path, "rev-parse", "HEAD").decode().strip()
    if actual != expected:
        raise ValueError(f"wrong exact pin: expected {expected}, found {actual}")
    if git(path, "status", "--porcelain", "--untracked-files=no").strip():
        raise ValueError(f"tracked source changes in {path}")

def archive(path, expected, destination):
    verify(path, expected)
    destination.mkdir()
    with tarfile.open(fileobj=io.BytesIO(git(path, "archive", expected))) as stream:
        stream.extractall(destination, filter="data")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in PINS:
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    receipt = {"pins": PINS, "scope": "Host production-feature source integration; not retained ELF execution or physical qualification", "runs": [], "negative_controls": []}
    for name, pin in PINS.items():
        verify(getattr(args, name), pin)
    # A real but wrong source checkout must not satisfy the other role's pin.
    for name, wrong in (("producer_system", "bridge"), ("bridge", "producer_system")):
        try:
            verify(getattr(args, wrong), PINS[name])
        except ValueError:
            receipt["negative_controls"].append({"role": name, "expected": PINS[name], "rejected_actual": PINS[wrong]})
        else:
            raise AssertionError("wrong pin accepted")
    recipe_bytes = git(args.product, "show", PINS["product"] + ":docs/t054/settings-command.json")
    assert hashlib.sha256(recipe_bytes).hexdigest() == RECIPE_SHA256
    recipe = json.loads(recipe_bytes)
    flags = [arg for arg in recipe if arg.startswith("-D")]
    assert len(flags) == 25 and "-DPORTABLE_LOW_BATTERY" in flags
    receipt["recipe_sha256"] = RECIPE_SHA256
    receipt["production_defines"] = flags
    receipt["harness_seams"] = ["Existing fixture RUNTIME_OVERRIDE and NAVIGATION_OVERRIDE disable only its capability/navigation fakes", "Existing fixture redefines SETTINGS_APP empty; definedness remains enabled, with no production logic change", "Original fixture main renamed and not invoked; its obsolete six-row expectation is not patched"]
    receipt["runner_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    receipt["target_options_not_replayed"] = [arg for arg in recipe if arg.startswith(("-m", "-Wl,")) or arg in ("-ffreestanding", "-nostdlib", "-nostartfiles", "-shared")]
    fixture = Path(__file__).with_suffix(".c").resolve()
    with tempfile.TemporaryDirectory(prefix="retained-settings-profile-") as td:
        root = Path(td)
        system, bridge = root / "system", root / "bridge"
        archive(args.producer_system, PINS["producer_system"], system)
        archive(args.bridge, PINS["bridge"], bridge)
        forced = [bridge / "apps/clock/faces/ContextsFaces.h", system / "test/native_apps/fixtures/watch_profile/watch-alarm-profile.h"]
        include = [system / "lib/PortableApps/include", system / "lib/NativeApps/include", system / "Apps", bridge / "sdk/app", bridge / "sdk/driver", bridge / "include", system / "test/native_apps"]
        sources = [fixture, system / "Apps/settings.c", bridge / "apps/clock/portable_navigation.c", bridge / "apps/clock/portable_sleep.c"]
        sources += [system / "lib/PortableApps/src" / name for name in ("quick_actions.c", "quick_render.c", "quick_session.c", "quick_radios.c")]
        actual = sources + forced + [system / "test/native_apps/portable_settings_test.c", system / "lib/PortableApps/src/adapter.c", system / "lib/PortableApps/src/settings.inc", system / "lib/PortableApps/include/PortableSleepPolicy.h"]
        receipt["source_sha256"] = {str(path.relative_to(root)) if path.is_relative_to(root) else path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in actual}
        base = [os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-Wno-unused-variable", "-g", *flags]
        receipt["host_compiler"] = subprocess.check_output([base[0], "--version"], text=True).splitlines()[0]
        base += [item for path in forced for item in ("-include", str(path))]
        base += ["-I" + str(path) for path in include]
        base += list(map(str, sources))
        def run(command, name, env=None, check=True):
            result = subprocess.run(command, capture_output=True, text=True, env=env)
            (args.output / (name + ".log")).write_text("COMMAND " + json.dumps(command) + "\n" + result.stdout + result.stderr)
            if check and result.returncode:
                raise RuntimeError(f"{name} failed ({result.returncode}); see log")
            return result
        missing = [arg for arg in base if arg != "-DPORTABLE_LOW_BATTERY"]
        rejected = run([*missing, "-fsyntax-only"], "negative-missing-low-battery", check=False)
        assert rejected.returncode and "Missing a required retained Settings feature flag" in rejected.stderr
        receipt["negative_controls"].append("missing LOW_BATTERY rejected by fixture before execution")
        exchanges = []
        for variant in ("plain", "asan-ubsan"):
            executable = root / ("settings-" + variant)
            sanitizer = [] if variant == "plain" else ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
            run([*base, *sanitizer, "-o", str(executable)], "compile-" + variant)
            env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1", UBSAN_OPTIONS="halt_on_error=1")
            for action in ("save", "cancel", "noop", "write-fail", "committed-error", "readback-fail", "exchange"):
                for which in range(3):
                    name = f"{variant}-{action}-{which}"
                    result = run([str(executable), action, str(which)], name, env)
                    row = json.loads(result.stdout)
                    receipt["runs"].append({"name": name, "result": row})
                    if action == "exchange" and variant == "plain":
                        exchanges.append(row)
        (args.output / "namespace1-records.json").write_text(json.dumps({"producer_system": PINS["producer_system"], "bridge": PINS["bridge"], "recipe_sha256": RECIPE_SHA256, "source": "actual all-feature Settings UI Save followed by reopen/readback", "profiles": exchanges}, indent=2) + "\n")
    receipt["passed"] = True
    receipt["limitations"] = ["Original Xtensa compiler/linker/ABI not replayed; no ELF byte identity claim", "Real local navigation and sleep linked; UI cases never request sleep", "Ready alarm and asynchronous display mocked; optional radios, broadcast and contexts unavailable", "No physical sleep, wake, input, display, current or live-memory qualification", "LeakSanitizer disabled in this ptrace environment; ASan and UBSan enabled"]
    (args.output / "settings-profile.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"passed": True, "runs": len(receipt["runs"]), "receipt": str(args.output / "settings-profile.json"), "records": str(args.output / "namespace1-records.json")}))

if __name__ == "__main__":
    main()
