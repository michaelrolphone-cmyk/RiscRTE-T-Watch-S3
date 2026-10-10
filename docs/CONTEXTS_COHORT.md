# Watch 1.0.15 navigation development cohort

This is a separate build lane. Accepted Watch 1.0.12, its receipts, historical
builders, Runtime 0.1.55 and all 22 installed provider artifacts remain intact.
The new lane rebuilds the 22 existing apps plus Contexts against explicit clean
source pins, preserving every existing grant and adding one
`contexts.service@1` grant per app. The launcher has 21 catalog entries.

The accepted store has 23 driver selections because the same I2C provider is
selected twice. Adding Contexts produces 24 selections, exactly the existing
graph bound. Apps use at most 15 policy grants, leaving one of the 16 live grant
slots for a temporary shared-settings acquisition. Board bytes, all prior
provider ELFs/manifests, and the paired native image identity are byte-frozen.

`apps/contexts-baseline.json` records the published accepted-store archive
digest, all 91 member digests, accepted cohort identity and original catalog.
The exact archive is required as an input; an optional unpacked baseline must
compare byte-for-byte. Contexts receives only shared KV namespace1 through the
Runtime's existing source-bound new-app migration. No source model namespace is
shared, reassigned, or granted to a new provider.

`apps/contexts-sources.json` distinguishes source manifest versions from rebuilt
deployment versions. Null System/Utilities pins are permitted only for staging
configuration tests. Target builds require all source pins and clean tracked
trees. The copied Contexts ABI headers must match exactly. The separate Clock
sidecar is `apps/clock/contexts-manifest.json`; accepted Clock sidecars remain
unchanged.

The Contexts Clock profile appends stable face ID33 in Compact Digital. Its
room/event labels are copied from fresh service status; paused, ambiguous,
malformed and stale observations render as unknown. Existing face IDs0–32 and
their stored selections are preserved. The additional face, cache state and
catalog entry are compiled only with `WATCH_CONTEXTS_CLIENT`; historical Clock
profiles retain their33-face layout. `ContextsFaces.h` exports the product's34
names to the generic preset editor.

Clock dispatches each source-owner export once through ordinary app launch. An
owner that fails to initialize or complete leaves an active request which the
next Clock invocation marks failed, avoiding an automatic launch loop. Alarm
output, Quick Controls, picker editing and sleep pause background capture. The
new service does not inhibit the accepted idle-sleep timer.

With the existing pinned Python build environment and GCC8.4 compiler:

```
python scripts/test_contexts_packaging.py --baseline /published/accepted-store.zip
TWATCH_CC=/path/xtensa-esp32s3-elf-gcc python scripts/build_contexts_cohort.py \
  --system-apps /source/system --utilities /source/utilities \
  --productivity /source/productivity --runtime /source/runtime \
  --drivers /source/drivers --baseline /published/accepted-store.zip \
  --unpacked-baseline /accepted/store --output /new/contexts-build
```

The builder reuses the established target input selection and semantic ELF
compactor. It validates target loader structure, imports/exports, complete C/C++
dependency ownership and absence of host fixtures. Uncompacted apps are retained
as debug custody. The original 22 providers are copied, never rebuilt.

Outputs are the complete `files/` store, `contexts-store.zip`, independently
round-tripped `contexts-bootfs.bin`, source/target build evidence, debug ELFs,
licenses and `contexts-apps.zip`. The fixed ABI2 SPIFFS geometry and two-block
reserve are enforced. The final verifier rechecks policy, exact file bytes,
compiler flags, compaction hashes and independently decoded bootfs contents.

These are development store artifacts. This builder does not rebuild Runtime,
produce an erase image, publish a release/catalog, or operate a device. Actual
installed-to-candidate Runtime admission, paired-update transaction proofs,
whole-cohort memory/cadence and physical Watch qualification are later gates.

## Native Runtime execution proof

`scripts/test_contexts_runtime.py` executes the production Runtime, CpuPort,
provider graph, provider sources and Clock over the existing lowest-hardware
fixture. It requires the exact candidate store and clean pinned sources. Host
app/provider modules use the same function/data section removal policy as the
new target builder; production JSON and granted namespaces remain unchanged.

Run once with `SANITIZE=0 ADDRESS_SANITIZE=0` and once with
`SANITIZE=1 ADDRESS_SANITIZE=1 ASAN_OPTIONS=detect_leaks=0`, both with and without
`--enabled`:

```
python scripts/test_contexts_runtime.py --watch . --runtime /source/runtime \
  --system /source/system --utilities /source/utilities --drivers /source/drivers \
  --store /new/contexts-build/files --output /new/runtime-proof --enabled
```

The enabled lane launches Clock, both real model-owner apps and Clock again.
It verifies private model reads only while each owner is active, empty saved
models, unknown input, ordinary cleanup, sleep acceptance/refusal and retained
sleep/capture cleanup failures. The disabled lane preserves the seven existing
startup/health/retention scenarios. These tests do not execute Xtensa
instructions or claim microphone/RF recognition on hardware.

Each run writes schema 2 `contexts-graph-proof.json`, binding the scenario
results to the candidate cohort, exact store digest and file inventory, source
commits/trees, source file hashes, fixture/runner hashes, sanitizer selection
and section removal flags. A source change during execution rejects the proof.

## Initial image gate

`scripts/build_contexts_initial.py` requires the target build, exact published
1.0.12 accepted store/provenance, verified 0.1.55 native inputs and all four
schema 2 execution reports, plus normal and sanitized model-import reports.
The model reports must be produced from this same clean Watch checkout.
It checks the current target dependency closure
and proof source hashes, reruns actual installed-to-candidate and self admission
in ordinary and ASan/UBSan modes, and only then assembles an initial image.
The original native candidate/provenance is included without rebuilding it.

```
python scripts/test_contexts_initial.py
python scripts/test_contexts_model_proof.py
python scripts/build_contexts_initial.py --build /new/contexts-build \
  --accepted /published/firmware-v1.0.12 --runtime /source/runtime \
  --native /verified/runtime-0.1.55 --system /source/system \
  --utilities /source/utilities --productivity /source/productivity \
  --drivers /source/drivers --runtime-report /proof/disabled-normal.json \
  --runtime-report /proof/disabled-sanitized.json \
  --runtime-report /proof/enabled-normal.json \
  --runtime-report /proof/enabled-sanitized.json \
  --model-runtime-report /proof/models-normal.json \
  --model-runtime-report /proof/models-sanitized.json --output /new/initial-candidate
```

This separate packager has no OTA mode. The explicitly named 16 MiB image at
offset zero erases saved settings, credentials, bonds, alarms, Points, all
app-data and both banks. Its output is an offline development candidate with
physical qualification pending; no release publication or device action is
performed. Output appears atomically after every required check passes.

## Preserved model-import increment

The preceding isolated product is 1.0.14. Contexts service/app 0.1.1 reuse saved temporal
positive/negative sequences and validated neural checkpoints exported by Audio
Spectrum 0.4.12 and Waterfall 0.2.8 through their own existing namespaces. Missing,
stale and invalid models remain explicit; Contexts does not train or write models.
Clock/default move to 0.10.9. Native 0.1.55 and the 22 earlier provider artifacts
stay byte-exact.

To fit the added inference code, only those five app deployments select GCC 8.4
link-time optimization. Their existing compiler support routines are explicit
link roots; the boot effect object keeps its original compilation mode. The new
service uses the existing verified metadata compactor, with its original ELF in
the debug evidence. The optimization policy remains unchanged in 1.0.15. All 22 app ELF/manifest
pairs other than Springboard must match the frozen 1.0.14 inventory in
apps/contexts-models-preserved.json exactly. The build refuses
to produce a verified store if any unrelated pair changes or capacity falls below
the existing two-block reserve. Runtime execution reports bind these optimization
choices as well as the exact source/store identities.

`scripts/test_contexts_model_runtime.py` adds five cases per instrumentation mode
using the actual Runtime, provider graph, Clock and both owner apps. Canonical
trainers create the test-only temporal banks and promoted neural checkpoints.
The real owners read their existing namespaces; the service must report the
expected positive/negative examples and temporal/neural readiness. Four more
cases return true AppData RETAINED at each owner's stat/read boundary and assert
no subsequent hardware, storage, display or module activity. Native PCM remains
empty, so these import cases do not claim recognition accuracy. They complement
the bounded capture/matcher tests in Utilities. See
`tests/contexts_models_store/README.md` for commands and scope.

This source is in development. A new image requires the complete target,
execution, allocation/relocation and initial-image gates; it is not a release.

## Nova page-swiping increment

Watch 1.0.15 changes only the Springboard deployment to 1.7.12. The complete
23-app target build verifies every other app ELF/manifest pair against the
qualified 1.0.14 store, while preserving the Contexts model service and native
Runtime. The same six Runtime reports and initial-image admission gates remain
required for the new exact source/store identity. This is an isolated navigation
development candidate; it does not overwrite either delivered Contexts image.
