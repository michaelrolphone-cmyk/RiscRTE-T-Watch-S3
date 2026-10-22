# T-Watch 1.1.46 inventory and consumer admission audit

**Generic serial pair: UNQUALIFIED / rejected.** This source-only deliverable
checks the complete declared core inventory and source-defined consumer boundary.
Passing these checks does not qualify a usable paired product, a preserving
update, a native build or hardware. CI evidence must name the exact published
source head. There is no installable manifest or container in this directory.

## Exact release and evidence level

- Repository base: `81dbde86969615f7378cc03c5800960a9092e076`.
- [Release 1.1.46](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/releases/tag/test-provisioning-1.1.46):
  upstream ID `415753487`, producer `ab9ff33975680c5bb8d9a2e7ed346d0300732a4e`.
- [Complete feed](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/blob/c2ea463a0bff968ce38e2a270aedfae7c49fefb4/native-packages-v1.json):
  12,674 bytes, SHA256 `2f08c10587344d3eb2ae07967a990ec1102719c9298582daa60037bd470549c3`.
- Runtime `48229bd1593a2e24e95bf4537b495ee615990fd3`, version `0.4.11`.
- Core: **125 files, 61 ELF and 64 JSON, 4,958,853 declared bytes**.
  The complete [human-readable matrix](inventory-consumers.md) and
  [machine-readable matrix](inventory-consumers.json) preserve every declared
  relative path, length and hash, identify its consumer evidence and explicitly
  leave its RTEF1 destination null. No row asserts execution.

The feed and 20 pinned source documents are read and hashed as text. Their exact
Git blob identities and SHA256 values are recorded in `source-lock.json`.
`release-metadata.json` is a normalized public GitHub API snapshot of all 19 asset
names, URLs, sizes and digests. `--fetch` rereads those public sources and metadata.
**Release binaries are not downloaded or freshly hashed by this audit.** The
125 per-file identities are verified declarations, not a new extraction of
`store.bin`; factory slices and native-loader receipts are not rerun here.

The retained public metadata agrees with the complete feed:

| Asset | Declared bytes | Published SHA256 |
| --- | ---: | --- |
| store.bin and content-addressed bootfs asset | 5,570,560 | e50d26000dc0366be61abbf480cd39ee98323ea5ef489536baf0cf7c4097b126 |
| firmware.bin | 1,624,560 | cd8f7f51d9c604e4f3b12b5f54dcc83817b812baa973b5862321a94e951f0034 |
| TWatch-1.1.46-Provisioning-factory-erases-data-0x0.bin | 16,777,216 | e132a6276cd444cd41482ecfcc2043296b2acf02ef882acc83ba1af4c76edff6 |

## What consumes the core, and what does not

The release producer's `provisioning_feed.py` requires all 125 core files and no
mirrors. `apps: []` and `profiles.core: []` are the separate dynamic-package catalog,
not absent bootstrap. The pinned System Apps feed builder binds the complete
store inventory to one exact image and native identity. Runtime `StoreFiles`
verifies every declared file and rejects missing or unlisted files. Runtime
`NativeBankStore` prepares/inspects the product and also admits extra ELF files;
its comments explicitly distinguish inspection from mapping, invoking or
executing modules. Therefore the common consumer classification is complete
core-profile verification and the firmware-owned paired boot store, not a claim
that every file executes or is selected by boot policy.

This release differs from historical 1.1.43: `package_provisioning.py` adds an
internal-package installation policy and the installed-apps/pkg-internal providers.
Do not carry forward 1.1.43's historical absence of installation authority as a
1.1.46 fact. That policy still does not expose its package workspace through RTEF1.
The producer retains its internal-only executable guard. Relevant immutable
sources are linked by ID in `source-lock.json`:

- `producer_feed`, `producer_package`, `feed_builder`: complete core, native
  identity, internal-only product composition and separate dynamic catalog.
- `store_files`, `bank_store`: complete readback, store admission and non-execution
  boundary, including extra/unselected ELF files.
- `native_profile`, `producer_profile`, `serial_selectors`, `serial_storage`:
  selected serial endpoint and namespace **2**, private `/appdata/.serial-files`;
  boot-store and SD serial selectors remain off in this product source profile.
- `package_volume`: separate `/appdata/.packages` internal package consumer.
- `appdata_files`: application roots `/appdata/n%08lx`.
- `mount_isolation`: distinct mount-custody roots, not namespace aliases.

Sharing the AppData partition does not route serial files to the package volume,
application data or the boot store. Copying a core file to namespace 2 does not
install or activate that core file. A storage label, provider instance, physical
root or numeric coincidence does not establish a generic consumer mapping.

## Capacity observations, not a new storage policy

The pinned partition CSV gives the *whole* AppData partition 524,288 bytes.
The feed declares `default.elf` alone as 554,744 bytes. `ReopenedFiles` reserves
139,264 bytes plus a 4,096-byte guard before permitting growth. These bounds
demonstrate why blindly copying this core into the private serial workspace is
not an admitted plan. They are **not** an installer budget, a free-space query,
a universal product limit or a decision to enlarge/change a backend. Existing
contents, metadata overhead, live provider state and consumer authority matter.

## Minimal unresolved contract

The frozen generic payload 1.0.0 contract requires a nonempty required-file
inventory, a target consumer and its evidence, an explicit admitted opaque
namespace mapping, accepted capabilities/limits/write budget and hardware
revision compatibility, plus a trusted release-specific manifest/container and
supported flash-method association. The complete bootstrap inventory already
exists; the missing piece is an accepted usable **generic serial destination and
consumer contract**, not a demand to pick SD, SPIFFS or LittleFS now.

The retained catalog review supplied with this work reported payload-plan revision
0 with null manifest/context and profile `watch` revision 0 without that accepted
namespace/budget/hardware-revision contract. That catalog state is contextual,
not fetched or asserted current by this public-GitHub-only audit. The existing
`esptool-full-0x0` implementation does not supply the missing trusted release
context. No placeholder, empty manifest or invented installable payload is emitted.

Factory bootstrap and a preserving generic serial update are distinct. Existing
factory delivery stays intact and carries the paired firmware/store; its release
warning says it erases data and provides no preserving update kit. Do not flash
the standalone firmware/store independently. A future legitimate generic pair
must prove its final consumer usability after the selected flash order; uploading
bytes first is not preservation evidence. Paired-catalog publication and physical
qualification remain gated by the recorded Waveshare pass.

## Reproduce this bounded audit

Python 3.10+ standard library only. From the repository at this draft's exact head:

```sh
python3 scripts/watch_payload_1146_audit.py --fetch --git-scope \
  --source-cache /tmp/watch-1146-source-cache --output /tmp/watch-1146-audit.json
python3 scripts/test_watch_payload_1146_audit.py \
  --source-cache /tmp/watch-1146-source-cache -v
python3 scripts/watch_payload_1146_audit.py --git-scope --require-paired \
  --source-cache /tmp/watch-1146-source-cache --output /tmp/watch-1146-refusal.json
# The final command must exit 2 and report "generic pair rejected".
```

The base commit must exist locally for `--git-scope`, and the tracked working tree
and index must match HEAD. HEAD attribution requires the committed docs location
and either the original exact nine-file additive scope or that scope plus the
complete 27-file companion delta retained in consolidation PR88. The latter pins
every companion path, add/modify status, Git mode and blob ID to PR87
(`697fac5510bb6a93119408edfa9c7ca8941f7ccf`, including PR84) and PR86
(`271bc06f84476fad37545d5ff8b575135a810f05`). Partial compositions, unexpected
paths, changed companion bytes/modes and changes to any other base file fail
closed. This composition does not change the release or product pins.
`--fetch` makes 20 bounded
text-source reads and one release-metadata read, each capped at 512 KiB with a
30-second timeout. It does not fetch any firmware, store, archive or factory
binary. An offline repeat uses the already verified source cache. Optional
`--write-matrix` regenerates only the two audit matrices deterministically.

The 31 regression tests cover standalone and complete composition success;
every companion blob/mode/missing-file mutation; partial, extra, renamed and
preserved-base source rejection; clean/dirty working-tree and index attribution,
alternate-docs refusal, the complete positive inventory, each of the 125
declared path/size/hash bindings with an exact-encoding positive control, all 20
source byte identities, missing/extra/duplicate
and overlapping files, unsafe paths, size/hash/type errors, ordering, false
mirrors or namespace aliases, source/release identity changes, source-root and
reserve regressions, schema emptiness, invented budgets/consumer/hardware claims,
tampered matrices, malformed JSON and online metadata mismatch.

## Source custody and publication boundaries

The initial GitHub checkpoint was explicitly UNQUALIFIED. The final exact source
head must be read back and qualified by the dedicated read-only CI, not by local
tests alone. That workflow has a seven-minute timeout, no secrets, no release
permissions, no firmware build and no dispatch/publishing step. Its result/log
artifact has seven-day retention and a `SHA256SUMS`; the immutable source files
remain in GitHub after the transient CI artifact expires.

All existing publication triggers were inspected at the base before branching.
This branch matches no firmware-publishing push route. The new directory avoids
the historical `docs/catalog-payload/**` trigger, so it does not rerun or replace
the frozen 1.1.43 asset audit. General inherited PR checks may also run and are
reported separately. Standalone diff checks permit only this directory, the two
new scripts and the new workflow, with no changes to existing base files. The
complete pinned consolidation additionally preserves the 25 additive companion
files and the exact two provisioning-release script modifications from PR86;
no other base-file changes are admitted.
The historical PR78/649b897 audit, production bytes, accepted pins, complete feed,
factory delivery and existing branches remain unchanged. No merge, tag, release,
catalog mutation, new storage implementation or hardware action is performed.
