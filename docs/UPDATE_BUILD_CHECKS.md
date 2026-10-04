# Update deployment local verification

This records the local source/test pass on 2026-10-04. It is not final Runtime
firmware CI custody, physical acceptance, or authorization to migrate a watch.
No final merged firmware BIN was created by these checks.

## Inputs

- Preserved delivered baseline: Watch `216e2d73b72cca6c3bcf75ad9ef56466b8861144`,
  Runtime `abef681d6c9c2b58729909a9961118ea20feee5e` (0.1.10).
- Local update pass: SystemApps `6a10b321c779d7ceb94b5143ab1257a4106f3664`,
  Utilities `5418d9dc7f9963d96b5b8b11c40658ee753d9cbd`, Productivity
  `43c23fee899cd2af8b6b5339b80e778018fb6295`, Runtime source
  `25fe7154a73a97c7584e31bec11001904fa597e4` (0.1.11 development candidate).
  Subsequent Runtime target fixes require a new exact source pin and committed CI
  rebuild; the live `apps/update-sources.json` is authoritative for future builds.
- Compiler: Xtensa ESP32-S3 GCC/G++ 8.4.0, esp-2021r2-patch5.
- SPIFFS tool: existing pinned Arduino ESP32 `tool-mkspiffs` 2.230.0,
  SHA256 `4ddf79a1ab9a3baf502cdb979bea7ed173bbe46727a9902649cc09e6a28a5ad2`.

## Verified

Each mode compiled its actual target apps and selected providers, built all eight
explicit source profiles, verified exact authority and preserved file hashes,
reconstructed the eight original ZIP hashes through common-store normalization,
and packed/unpacked a 5,177,344-byte SPIFFS image with exact file equality.

| Mode | Apps | Store files | Payload bytes | Integration fixtures |
| --- | --- | --- | --- | --- |
| paired | 11 | 44 | 2,508,813 | 10 pass, including 2 inapplicable provider tests skipped |
| ota | 12 | 48 | 2,645,732 | 10 pass |
| all | 13 | 52 | 2,783,310 | 10 pass |

The two skipped paired-only tests require an updater/provider to mutate; common
custody, baseline authority, layout, catalog, old ELF preservation, and mode
selection checks still run. `UPDATE_DEPLOYMENT_DIR` can select preserved stage
ZIPs when rerunning `tests/test_update_deployment.py`; its default is the active
`dist/update-launcher-deployments` lane.

Negative fixtures rehash modified ZIP entries before checking semantic rejection:
extra/raw-native/cross-namespace grants, wrong service kinds or instance IDs,
provider KV authority, changed source and target hashes, missing/extra store files,
changed old executables, wrong Clock versions, altered layout/profile data,
unapproved catalog entries, changed return targets, missing/duplicate hardware
profiles, and forged original common-archive hashes.

Both update apps have portable version 1.1.0. Their legacy SystemApps metadata is
unchanged. Springboard uses its exact pinned source version and catalog addition;
its existing authority is unchanged. The returning Clock ELF is byte-identical to
the delivered baseline even though its paired manifest version is 0.7.1.

The frozen Wi-Fi lane was separately recompiled using its old source pins and
packaged through the default `updates=None` builder path. All 44 store files in
all eight hardware profiles matched the delivered 216e2d73 bytes exactly,
including the original default/return Clock and Springboard.

Native provider binaries are independently pinned in the source baseline:

| Provider | ELF bytes | BSS bytes | SHA256 |
| --- | --- | --- | --- |
| firmware | 24,848 | 645,456 | `2163dcc0da56f052b2cf551f4b026375dad77bc1a155f6e91b4c2747cf15f5d9` |
| apps | 25,532 | 649,552 | `f67e45d3fcbaadcb02a329cd72f8aee5b80718c3e2846966e75573f1ed18c6a3` |

These ELF hashes came from the clean pinned SystemApps source and its canonical
provider build script. They establish reproducibility of those providers; they do
not establish successful native Runtime target compilation, free RAM on hardware,
TLS connection latency, OTA rollback behavior on a device, or final artifact custody.

## Recovery and durable publication, 2026-10-04

The development workspace was replaced after the earlier local qualification.
The published Runtime0.1.11 head76212b70 and its successful CI37202528313 remain
available. Its paired artifact11303128669 has been downloaded again and matched
to the hosted7,030,843-byte ZIP digest; the committed update-runtime-artifact.json
now records exact component custody. The separate SystemApps updater branches
include the final cancel/retry and uncertain-activation UI fixes.

This checkpoint restores the pending branch-mode/typed-sidecar/atomic-publication
checks, checked TLS-close fixture, and current source pins. Focused Python tests
were rerun after recovery. Historical local evidence cited above is not evidence
of a new recovery run; every final Watch branch must pass its own exact-head CI.
The final flashing-image assembler remains gated on that CI receipt, native
artifact reproduction, actual store admission, and default Clock execution on
the final extracted store. No recovery-time device operation or BIN delivery is
claimed here.
