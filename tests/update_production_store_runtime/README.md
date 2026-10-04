# Paired update-store admission and Clock health

This is an additive update-only lane. The delivered Clock/store regression in
`tests/production_store_runtime` and `scripts/test_production_store_runtime.py`
remains unchanged, including its Runtime 0.1.10 contract. The new host fixture
reuses its real lowest-hardware model and has independent update assertions.

`scripts/update_test_production_store_runtime.py` exports:

- `admit_many(runtime_source, stores, output=None)`
- `execute_many(runtime_source, system_apps, utilities, productivity, stores, output=None)`
- `verify_clock_abi(runtime_source, output=None, compiler=None)`

`stores` is a list of `(label, {relative_path: bytes})` pairs. This lets the
paired assembler supply every actual profile ZIP, common store, SPIFFS-extracted
store, and store extracted from the final BIN through the same gate without
reusing legacy single-bank offsets. `--store`, `--archive`, and raw partition `--image` (with `--mkspiffs`)
are available for standalone runs. Image inputs require the paired layout/ABI,
bootfs0 label, pinned extraction parameters, byte count, filename and digest in
the companion JSON. No full-BIN offsets are inferred. Ordinary CLI execution
first admits every untouched store, then executes every host-source copy. Keep generated evidence with `--output DIRECTORY`. Runtime
source identity is checked and all relevant source/header hashes are recorded.

Admission uses the real Runtime, CpuPort and provider graph. The complete native
HTTP table binds through CpuPort; the bank table is registered only by the native
port. Every actual production policy, board and driver manifest remains byte
identical. Hardware and storage call counters must remain zero during admission.
The paired default manifest must be 0.7.1; Clock/Points retain namespaces 1 and 5.
When present, each updater has exactly eight grants: display 5, touch 6, RTC 8,
battery 4, KV namespace 6, Wi-Fi 15, its update service 0, and alarm service 0.

Execution replaces only selected executable bytes in a separate host copy. It
compiles production Watch drivers, the real Points-enabled alarm service, both
selected update service sources, and actual paired Clock crown/effects/Points
sources using the delivered feature flags. It runs these cases for every store:

- Healthy startup: the native confirmation callback observes a complete nonzero
  Clock frame, brightness after full frame transfer, touch polling, and actual
  Clock settings/Points reads. Confirmation happens once before the ready log.
- Health lost before startup: no complete frame and no confirmation.
- Health lost during the first transfer: the actual Clock drains the accepted
  frame and exits without confirmation.
- Native confirmation refusal: Clock exits without its ready diagnostic.
- Native-retained state immediately before confirmation: Runtime refuses the
  callback and retains the invocation/graph rather than treating exit as health.
- Missing provider-only bank table: stores selecting an updater fail graph
  admission before any module, hardware, storage, or confirmation operation.

On healthy/refused/early exit paths, all actual app/provider modules unload and
hardware resources quiesce. No test may use RF, update transport/bank I/O, RTC
writes, persistent writes, restart, or any real credentials. The healthy callback
also proves that apps cannot acquire the raw HTTP or bank tables.

The established Runtime `test/run_update_runtime_test.sh` runs unchanged to cover
module init/fini, child apps, queued handoff, intentional exit, retention, and
update policy ownership; this lane does not invent a duplicate ownership stack.

The ABI test places the frozen prefix against a guard page and checks every
short/partial advertised table size, null/mismatched tables and null callbacks.
It executes with both frozen Watch and canonical Runtime headers. With required `TWATCH_CC`
(or the compiler on PATH), both variants also compile for Xtensa
with static assertions proving the 32-byte frozen prefix, callback offset 32,
and complete appended suffix size 36. No frozen SDK header is changed.

UBSan is on by default. `ADDRESS_SANITIZE=1` also enables ASan; intentional native
retention is checked in an isolated process that exits without destroying its
intentionally retained owner/graph, matching the production lifetime contract. These are
host-source integration tests and target ABI compilation, not Xtensa execution,
physical first boot, RF qualification, flashing, or a release claim.

All paired stores now use Runtime's production target module registry
(dlfcn.c/dlmod.c), with only relocation delegated to native host mappings.
This covers same-basename hardware, Alarm and update providers before default
Clock startup and boot-health confirmation. The helper implementation and actual
registry sources are included in each execution's source hash inventory.
