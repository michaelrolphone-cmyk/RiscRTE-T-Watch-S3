# Contexts 1.0.13 development cohort

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
