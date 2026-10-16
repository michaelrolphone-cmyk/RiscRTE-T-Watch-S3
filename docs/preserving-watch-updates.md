# Exact-origin preserving update qualification

The update payload contains only native firmware followed by the complete
inactive boot store. It contains no bootloader, partition table, NVS, or app-data
image. A full 16 MiB initial image is a separate destructive artifact.

`apps/preserving-update-profile.json` binds the four input image digests and the
unchanged Runtime 0.1.55 firmware. The package builder refuses other source bytes.
No script here publishes a release, updates a live catalog, or accesses a device.

Two routes are necessary with the installed Runtime and catalog protocol:

| Installed source | Candidate | Policy change |
| --- | --- | --- |
| Exact delivered 1.0.12 | Exact delivered 1.0.15 | Its existing source-bound grant for the new Contexts app |
| Exact delivered 1.0.13, 1.0.14, or 1.0.15 | Packaging candidate 1.0.16 | Retire the consumed migration; all existing grants remain identical |

The 1.0.16 qualification candidate keeps every 1.0.15 executable, provider and app
manifest byte unchanged. Only `boot.json` and `cohort.json` differ. It is an
isolated packaging proof, not the next feature release. The subsequently found
Audio/RF retained-cleanup correction belongs to the separate 1.0.17 app stage.

The old provider parses one `firmware` record at a fixed catalog URL. It cannot
choose these two routes by installed source. Therefore these generated catalog
fixtures must not be published as a universal update offer. Native admission
rejects the incompatible route, but that rejection does not provide automatic
routing. The source-bound bridge and newer Contexts lineage must remain explicit
until deployment routing is implemented and qualified.

## Reproduce the prepared packages

Use the exact frozen 1.0.15 full image, the clean Runtime commit named in the
profile, and a Python environment with the repository's build dependencies.
Each output directory must be new.

```sh
python scripts/build_preserving_watch_update.py \
  --baseline-image /path/to/exact-1.0.15-initial.bin \
  --runtime /path/to/exact-runtime \
  --output /path/to/new-1.0.16-package

python scripts/build_preserving_watch_update.py --bridge-from12 \
  --baseline-image /path/to/exact-1.0.15-initial.bin \
  --runtime /path/to/exact-runtime \
  --output /path/to/new-1.0.15-bridge
```

The ordinary builder also emits a full initial image to give its catalog
fixture a real outer image digest. That image erases user data. Its existence
does not qualify physical installation or authorize distribution.

## Qualify each exact route

Run `scripts/test_preserving_watch_upgrade.py` with `--origin-image`,
`--origin-version`, `--target`, `--runtime`, `--native`, and a new `--output` JSON.
Repeat with `SANITIZE=1 ASAN_OPTIONS=detect_leaks=0`. Each mode checks 31 fault,
cancellation, corruption, activation and success scenarios through 159 fresh
processes plus 16 negative store admissions. It compares NVS, app-data, the
original native/store pair and its journal byte-for-byte after every process.
ASan and UBSan run; LeakSanitizer is disabled in the traced execution environment.

`scripts/test_preserving_update_service.py` additionally takes `--system-apps`
and runs the exact catalog and payload through the installed production updater
source. It covers download/activation, cancellation, retained HTTP cleanup and
a changed installed identity, in normal and sanitizer modes. Its dependency
closure must match the accepted System source even when a later checkout is used.

These are complementary proofs. The transaction proof runs the real Runtime,
native bank API, hashing and graph/ELF validator over modeled IDF flash and file
views. The updater proof runs the actual provider over explicit HTTP/native-bank
doubles. Neither executes Xtensa instructions, physical TLS or SPIFFS, real
bootloader selection, or device health confirmation. Those limits remain visible
in every receipt.

## Final 1.0.17 native pair

The separate `bound_preserving_watch_update.py` packager verifies the immutable
Watch17 binder b6abe35 and canonical Runtime b587df55 (0.1.73) before composing
paired bytes. Every app/provider/policy file remains equal to the frozen stage;
this operation does not rebuild applications. Its paired payload is exact native
firmware followed by exact bound SPIFFS bytes. Its separate 16 MiB initial image
contains empty NVS/app-data and must never be used as a preserving update.

`test_bound_preserving_upgrade.py` runs the existing complete transaction matrix
from each exact delivered 1.0.13, 1.0.14 and 1.0.15 origin. Admission and staging
execute the installed Runtime0.1.55 source; candidate boot and rollback execute
Runtime0.1.73. Both native ELFs remain tied to their actual source/bytes. Watch12
still requires its separately qualified delivered15 bridge. This does not remove
the installed clients' single-record catalog routing limitation.

## Actual two-hop bank direction

Direct origin tests begin with a full initial image in bank0. They alone do not
qualify a two-hop Watch12→15→17 upgrade, which must return through bank1→0.
`test_preserving_watch_chain.py` therefore runs the complete first-hop matrix,
exports its actual selected flash snapshot, and uses that snapshot as the next
installed origin with bank1 active. It keeps the first hop's NVS/app-data bytes
without replacing them with a new test pattern. The second full matrix stages
Watch17 into bank0 and preserves the complete bank1 rollback pair.

Both exported snapshots are host-model evidence, not flashable user images.
IDF boot selection/confirmation remains explicitly modeled. The runner does not
claim that separate direct routes establish a tested two-hop sequence.

## Published proof-source checkpoint

This isolated branch carries the preserving tools on the public Watch1.0.13
source lineage. It changes no selected product version, app inventory, driver
pin, release index or provisioning payload. The original loaded Python
dependency closure, native fixtures and selected profiles matched tested
source8e5c332. Their historical hashes remain recorded in
`docs/evidence/watch117-preserving/source-custody.json`; explicitly listed
verifier follow-up files now supersede the relevant source hashes.

The recorded final result is1,590 fresh-process executions and160 negative
native admissions, covering all direct13/14/15→17 routes and the actual
12→15→17 bank0→1→0 chain, normally and under ASan/UBSan. The normal and sanitizer
results agree except for the sanitizer flag. The installed update provider
adds32 executions and24 catalog-identity rejections;12 package mutations verify
complete-image placement, scope, notices and checksums. The compact evidence
record hashes every original detailed receipt. These are existing software
qualification results, not a claim that routine PR CI re-runs the full matrix.

To reproduce, supply the exact origin images identified by the profile, the
original Runtime0.1.55 source/native candidate, final Runtime0.1.73 source/native
candidate, and the separate original Watch binder b6abe35 restored from the
provisioning source bundle. Use `--help` on the bound package, transaction,
service and chain scripts for their explicit path arguments. Watch PR53 owns
the initial provisioning wrapper. Source pins and embedded build identities
remain the originals; this checkpoint does not relabel the binaries.

## Verifier admission follow-up

The original 1,590-process and 160-negative-admission receipts above remain
historical evidence. The verifier hardening does not claim a new run of that
matrix, change any native or product bytes, or qualify physical execution.
Its source changes are listed separately under `verifier_followup` in the
source-custody record. The full loaded closure additionally includes the
dynamic ELF admission helper and two import-time baseline JSON inputs.

Package verification now requires an independently selected package-builder
commit and the exact complete initial-image metadata object. The proof runners'
`--packager-source` defaults to the frozen package's builder7cba7a1. Supply the
actual, independently known builder commit when qualifying a newly built
package; never select it from that package's untrusted receipt. Building a new
package checks it against the current clean builder commit automatically.

Graph and transaction compilation use the compiler's non-system dependency
closure and compare every consumed repository input with its pinned Git blob
before and after compilation. This rejects untracked or ignored headers that
shadow tracked inputs. Freshly generated headers and previously checked object
files are allowed only with exact expected bytes. Host compiler/system headers
remain the toolchain boundary. Compiler-selected precompiled headers are
rejected because their contents can differ from the tracked textual header.
The focused compiler-custody regressions run in
ordinary PR CI; the expanded package-mutation runner requires the separately
supplied frozen artifacts. These follow-up checks are distinct from the
historical preserving matrix.
