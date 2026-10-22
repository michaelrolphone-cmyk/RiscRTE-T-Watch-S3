#!/usr/bin/env python3
"""Read-only exact-source checks for retained T-Watch 1.1.46 power records.

This does not rebuild or execute a retained Xtensa ELF. It compiles the documented
historical Settings producer and selected Home header independently on the host.
No device access, release mutation, or production-source edit is performed.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

PINS = {
    "producer_system": "9dcb2bbef44853e533d980a658a814d2c787a4fa",
    "selected_system": "bb0cadf3cec3445a64e11513b47b2676f3fdd92d",
    "watch": "416fa9f144fa5bd5471e6f4c9cefff21455c8361",
}
HASHES = {
    "producer_system": {
        "Apps/settings.c": "2af07dfa4c19d8c1fd3f652fb052a33d40611a4c545e77ac7298328486626bd6",
        "lib/PortableApps/src/settings.inc": "a20e0410b91bcac24459e720469afbe40af8397df918480e33b470a5a2c23fbe",
        "lib/PortableApps/include/PortableSleepPolicy.h": "8d4b92e1f230bf13ad885dbc3f6a51f7a459d229703301d433124ccb428e557a",
        "test/native_apps/portable_settings_test.c": "da9ed05d949b1f347b8811c86e918e53c053511583b1b201b87e47fc264948d7",
        "test/native_apps/portable_sleep_policy_test.c": "4412e3045a70658af90d971564785ea21ee859287ad2f3a6cb6db82a90412d3e",
        "scripts/test_low_battery.py": "a500f60a4ef626092eeaa052ecced9b35da601996262a22653bd1f6e868810cb",
        "test/native_apps/low_battery_test.c": "12ea2dfcfa4101615c8eba8df07f2854a8b21aa0352364b031e6348a1ab487be",
        "test/native_apps/low_battery_adapter_test.c": "7114a3aea42ab0136612b7a0027356a4a1b77b1a75f98efd825b00f325407d2c",
    },
    "selected_system": {
        "lib/PortableApps/include/PortableSleepPolicy.h": "70fa8ff8f63270b2a04d591bdbc61cd7e16d6483421121a96fe22f2855966d9d",
        "lib/PortableApps/src/quick_session.c": "7b2313c4f1a67f1c3ba2398c65851aad3c5c92b59f69534b5900d1362dc92c96",
    },
    "watch": {
        "apps/clock/PortableSleepPolicy.h": "b0251ad4e4c25a4842ad19c1f998f9fb60a3ee2577f49784417d7db880d33995",
        "apps/clock/crown.c": "78d867e6349c38231d6902a6530affa50e26b719147f7af7749e2e9379ed4891",
    },
}

# Storage is a five-byte mock only. Encoding, validity, no-op and readback are
# production functions from each immutable source tree, never reimplemented.
FIXTURE = r'''
#ifdef SELECTED_HOME
#include "apps/clock/PortableSleepPolicy.h"
#else
#include "PortableSleepPolicy.h"
#endif
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned char blob[5];
static uint32_t length;
static unsigned writes;
static int32_t get(void *c,const char *k,void *out,uint32_t cap,uint32_t *n) {
 (void)c;assert(!strcmp(k,"sleep_idle")||!strcmp(k,"sleep_deep"));*n=length;
 if(!length)return RISC_KEY_VALUE_NOT_FOUND;
 if(cap<length)return RISC_KEY_VALUE_BUFFER_SMALL;
 memcpy(out,blob,length);return RISC_KEY_VALUE_OK;
}
static int32_t put(void *c,const char *k,const void *in,uint32_t n) {
 (void)c;assert(!strcmp(k,"sleep_idle")||!strcmp(k,"sleep_deep"));
 assert(n==sizeof(blob));memcpy(blob,in,n);length=n;++writes;return RISC_KEY_VALUE_OK;
}
int main(int argc,char **argv) {
 assert(argc==2);risc_key_value_v1 kv={1,sizeof(kv),0,get,put};
 if(!strcmp(argv[1],"produce")) {
  unsigned deep;uint32_t ms;
  while(scanf("%u %u",&deep,&ms)==2) {
   assert(deep<=1);length=writes=0;
   bool saved=portable_sleep_timer_save(&kv,deep,ms);
   if(saved){assert(writes==1);assert(portable_sleep_timer_save(&kv,deep,ms));if(ms)assert(writes==1);}
   printf("%u %u %u %u ",deep,ms,saved,length);
   for(unsigned i=0;i<length;i++)printf("%02x",blob[i]);
   puts("");
  }
 } else {
  assert(!strcmp(argv[1],"consume"));unsigned deep,n;char hex[11];
  while(scanf("%u %u %10s",&deep,&n,hex)==3) {
   assert(deep<=1&&n==5&&strlen(hex)==10);length=n;
   for(unsigned i=0;i<n;i++){unsigned v;assert(sscanf(hex+2*i,"%2x",&v)==1);blob[i]=(unsigned char)v;}
   uint32_t ms=0;int status=portable_sleep_timer_load(&kv,deep,&ms);
   printf("%d %u\n",status,ms);
  }
 }
 return 0;
}
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def verify(role, repo):
    actual = git(repo, "rev-parse", "HEAD").decode().strip()
    if actual != PINS[role]:
        raise ValueError(f"{role}: expected {PINS[role]}, got {actual}")
    subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "HEAD", "--"], check=True)
    for name, expected in HASHES[role].items():
        if digest((repo / name).read_bytes()) != expected:
            raise ValueError(f"{role}: source hash mismatch: {name}")


def snapshot(repo, target, paths):
    target.mkdir()
    with tarfile.open(fileobj=io.BytesIO(git(repo, "archive", "HEAD", *paths))) as archive:
        for member in archive.getmembers():
            if Path(member.name).is_absolute() or ".." in Path(member.name).parts:
                raise ValueError("unsafe archive path")
            if not member.isfile() and not member.isdir():
                raise ValueError("unexpected archive entry")
        archive.extractall(target, filter="data")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for role in PINS:
        parser.add_argument("--" + role.replace("_", "-"), type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repos = {role: getattr(args, role).resolve() for role in PINS}
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for role, repo in repos.items():
        verify(role, repo)
    # Exercise the real verifier with the wrong source, not an expected-value
    # comparison that could silently stop policing source custody.
    try:
        verify("producer_system", repos["selected_system"])
    except ValueError as error:
        negative = {"wrong_selected_as_producer_rejected": True, "reason": str(error)}
    else:
        raise AssertionError("wrong-source negative control was accepted")
    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0", UBSAN_OPTIONS="halt_on_error=1")
    runs = []

    def run(name, command, stdin=None, timeout=180):
        result = subprocess.run(list(map(str, command)), input=stdin, capture_output=True,
                                text=True, env=env, timeout=timeout)
        log = output / (name + ".log")
        log.write_text(result.stdout + result.stderr)
        runs.append({"name": name, "command": list(map(str, command)),
                     "returncode": result.returncode, "log": log.name,
                     "log_sha256": digest(log.read_bytes())})
        result.check_returncode()
        return result.stdout

    matrices = []
    with tempfile.TemporaryDirectory(prefix="retained-power-source-") as temporary:
        work = Path(temporary)
        source = {}
        for role, paths in {
            "producer_system": ["Apps", "lib", "test/native_apps", "scripts/test_low_battery.py"],
            "selected_system": ["lib/PortableApps/include"],
            "watch": ["apps/clock/PortableSleepPolicy.h"],
        }.items():
            source[role] = work / role
            snapshot(repos[role], source[role], paths)
        producer = source["producer_system"]
        cc = os.environ.get("CC", "cc")
        base = [cc, "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror"]
        sanitizer = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                     "-fno-omit-frame-pointer", "-no-pie"]
        includes = ["-I" + str(producer / "lib/PortableApps/include"),
                    "-I" + str(producer / "lib/NativeApps/include")]
        mode = work / "settings-mode"
        run("compile-original-settings-mode", [*base, *sanitizer, *includes,
            "-DPORTABLE_SLEEP_SETTINGS", producer / "Apps/settings.c",
            producer / "test/native_apps/portable_settings_test.c", "-o", mode])
        for case in range(40, 48):
            run(f"original-settings-mode-{case}", [mode, case])
        policy = work / "sleep-policy"
        run("compile-original-sleep-policy", [*base, *sanitizer, *includes,
            producer / "test/native_apps/portable_sleep_policy_test.c", "-o", policy])
        run("original-sleep-policy", [policy])
        run("original-low-battery-runner", [sys.executable, producer / "scripts/test_low_battery.py"])
        fixture = work / "records.c"
        fixture.write_text(FIXTURE)
        # Every ordinary editor choice reachable from its default by 5s/60s
        # steps, followed by inherited-record boundaries and rejected writes.
        cases = [(deep, seconds * 1000, "ordinary-ui-bounded")
                 for deep, step in ((0, 5), (1, 60))
                 for seconds in range(step, 3601, step)]
        cases += [(deep, seconds * 1000, "persisted-contract-boundary")
                  for deep in (0, 1) for seconds in (0, 1, 4, 5, 59, 60, 3599, 3600, 3601, 14400, 14401)]
        cases += [(deep, 60001, "non-whole-second-rejected") for deep in (0, 1)]
        inputs = "".join(f"{deep} {ms}\n" for deep, ms, _ in cases)
        for sanitized in (False, True):
            binaries = {}
            for role in ("producer_system", "selected_system"):
                exe = work / f"records-{role}-{int(sanitized)}"
                flags = ["-I" + str(source[role] / "lib/PortableApps/include")]
                if role == "selected_system":
                    flags += ["-DSELECTED_HOME", "-DWATCH_SHARED_PREFERENCE_HEADERS",
                              "-I" + str(source["watch"])]
                run(f"compile-records-{role}-{int(sanitized)}",
                    [*base, *(sanitizer if sanitized else []), *flags, fixture, "-o", exe])
                binaries[role] = exe
            produced = run(f"produce-records-{int(sanitized)}",
                           [binaries["producer_system"], "produce"], inputs).splitlines()
            assert len(produced) == len(cases)
            accepted = []
            for case, line in zip(cases, produced):
                deep, ms, category = case
                fields = line.split()
                actual_deep, actual_ms, saved, size = map(int, fields[:4])
                assert (deep, ms) == (actual_deep, actual_ms)
                expected_saved = ms % 1000 == 0 and (ms == 0 or (60000 if deep else 5000) <= ms <= 14400000)
                assert bool(saved) == expected_saved
                if saved:
                    assert size == 5 and len(fields) == 5
                    accepted.append((deep, ms, category, fields[4]))
                else:
                    assert size == 0
            record_input = "".join(f"{deep} 5 {record}\n" for deep, _, _, record in accepted)
            reads = {}
            for role, exe in binaries.items():
                reads[role] = [tuple(map(int, line.split())) for line in run(
                    f"consume-{role}-{int(sanitized)}", [exe, "consume"], record_input).splitlines()]
                assert len(reads[role]) == len(accepted)
            differences = []
            for index, (deep, ms, category, record) in enumerate(accepted):
                historical = reads["producer_system"][index]
                current = reads["selected_system"][index]
                assert historical == (0, ms if ms else 0xffffffff)
                expected = (0, ms) if 0 < ms <= 3600000 else (2, 300000 if deep else 60000)
                assert current == expected
                if category == "ordinary-ui-bounded":
                    assert historical == current
                if historical != current:
                    differences.append({"deep": bool(deep), "milliseconds_written": ms,
                                        "record_hex": record, "historical_read": historical,
                                        "selected_home_read": current})
            assert len(differences) == 6
            matrices.append({"sanitized": sanitized, "producer_cases": len(cases),
                             "ordinary_ui_bounded_cases": 780,
                             "accepted_records_read_by_each_consumer": len(accepted),
                             "persisted_record_differences": differences})
    receipt = {"status": "passed", "git_pins": PINS, "source_sha256": HASHES,
               "script_sha256": digest(Path(__file__).read_bytes()),
               "negative_control": negative, "matrices": matrices, "runs": runs,
               "original_fixture_counts": {"mode_cases": 8, "sleep_policy_programs": 1,
                                           "low_battery_program_runs": 38},
               "scope": "Exact historical source controller/policy host tests plus independent real-header record exchange; not exact retained Xtensa ELF execution or a full compile-flag replay.",
               "observed_boundary": "Ordinary retained timer UI choices agree. Historical records 0 (Off sentinel), 3601s and 14400s are accepted historically but rejected by selected Home, which falls back to 60s idle/300s deep. This is a persisted-record compatibility boundary, not a demonstrated ordinary UI defect or whole-product failure.",
               "not_qualified": ["physical sleep entry", "physical wake", "physical input",
                                 "physical display recovery", "current consumption", "live memory"]}
    (output / "source-checks.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": "passed", "receipt": str(output / "source-checks.json"),
                      "ordinary_ui_cases_per_matrix": 780, "historical_fixture_runs": 47,
                      "persisted_record_differences_per_matrix": 6}))


if __name__ == "__main__":
    main()
