# Shared Home on the recovered T-Watch: source-only checkpoint

This recipe starts at the complete, recovered **1.1.21-r1** image and source
`b5ed35f93792cd34a0c6df30895767a708a98658`. It never starts from 1.1.17.
It verifies the exact image and its 113-file / 55-ELF inventory before selecting
any new bytes. This is not a firmware release or a flashable image.

## Selected components

- Shared Home source: `ec768c7fae6fdb484fef28c6ec87f129b0a7f585`
- `default.elf`: 871,088 bytes,
  `7397f8ba6a036299a71bf7c62ba7882065e9ffca0ea87f0175a7eb35908cfbc1`
- `clock.elf`: 1,232 bytes,
  `cfd7de71d1949e415ba6662862feba4733e384258670ec73760425436d3fcde1`;
  this is already the identical retained return module, not another Home
- Home's System dependency: `076f8da38f7dfebdfde6dd5d46e06446470fb828`
- Home's Utilities dependency: `fc0bdbbbc600ce891e60c44d091fce0586ade7d8`
- Exact Home build receipt: SHA-256
  `1ef09445da264389483c576d5e943f56eaac120ae2c7eaa01bba62b4b69532dc`
- Retained native source: `06da76aa7f074220b74a282badca0ed0061f1643`
- Retained native BIN: SHA-256
  `1477f28bad4bf78faa7e29eb5082421b84050e5f160bc12e4e92a74ca2ce701f`
- Retained formatted appdata: 0x270000..0x2f0000, SHA-256
  `5f03c248f2de31c4da9ae8d9bc2033df064cee5e37694a9982f70fbb2f1d2ef0`

The recipe verifies the exact build receipt, all 124 Home-source input hashes
against the pinned Git commit, source manifests, the shared stager, the full
feature flag list, dependency receipts, loader-preserving compaction and both
ELF hashes. The checkout may be on a newer branch because source reads use the
exact immutable commit. It does not compile anything or trust current checkout
files as a substitute for that commit.

All other application/provider ELF bytes remain identical. Existing namespace,
shared-file and instance selections remain intact. Default gets three independent
generic instance-0 grants: `power.sleep`, `input.power-key`, `display.power`.
They remain **unresolved** until qualified device providers are selected.
The original cohort and native bank data are deliberately not rebound. The
unsealed overlay must not be provisioned as if it were an admitted cohort.

Settings/Springboard are not replaced. The historical optional bridge/System UI
pins in the selection are reference candidates only; newer unrelated app repairs
must never be replaced by a blanket System build. UI selection additionally awaits
the shared runtime application-catalog correction and exact target artifacts.

## Audit of the public predecessor

The public [`27505625` integration](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/commit/27505625b29031de4d2347a37fbc1ef82176ad67)
was read through GitHub. Its assembler verifies and overlays the older 1.1.17
image, selects Home `76aa4772`, and replaces native code with Runtime `5323d1e8`.
Its eight-free-block claim applies to that older composition. Those pins and its
full-image composition path are **not selected here**. Useful reusable structure
is the shared product stager and the requirement for complete native/store
admission before writing any firmware. The recovered native repairs are not
assumed equivalent to the historical generic Runtime.

## Capacity, with no filesystem image generated

The immutable SPIFFS partition is 0x510000 bytes: 1,296 blocks of 4,096 bytes.
The unchanged minimum reserve is two blocks. Exact allocation counts use the
hash-pinned existing ESP-IDF generator, but never call its image serializer.
The bounded analytical counter can count up to 64 overflow blocks; all admission
is evaluated against the real 1,296-block geometry, never the scratch bound.

- Recovered store: 1,294 occupied, 2 free; meets reserve
- Shared Home ELF alone: 1,297 occupied, -1 free
- Complete Home-only staging, including generic grants: 1,297 occupied, -1 free;
  needs three additional free blocks before adding provider bytes
- Explicit unsigned-JSON compaction: 1,296 occupied, 0 free;
  still needs two additional free blocks before adding provider bytes

The baseline boot.json is already compact. Optional compaction of other unsigned
JSON saves 3,258 bytes in the staged store. It checks parsed semantic equality,
skips signature-bearing/nested-signed documents, and retains cohort bytes.
No JSON compaction is enabled by default. No font, feature, app or provider is
removed. These counts are not a successful production SPIFFS round trip.

## Run

The inputs below are existing verified artifacts, not files produced by this
checkpoint. The output path must be new.

```sh
python scripts/stage_watch_shared_recovery.py \
  --baseline-image /path/to/T-Watch-S3-1.1.21-r1-AppData-Fix-full-0x0.bin \
  --shared-source /path/to/RiscRTE-Watch-git-repository \
  --shared-apps /path/to/exact-shared-Home-build \
  --output /path/to/new-source-staging
```

An optional separate measurement adds `--compact-unsigned-json`.
Outputs are `UNSEALED-OVERLAY/`, `staging.json`, and `NOT-FLASHABLE.txt`.
There is no firmware, bootfs image, native build, bank record or flash action.
A successful command exit means source staging succeeded; the receipt's
`flashable: false`, capacity failure and pending admission remain authoritative.

```sh
WATCH_SHARED_RECOVERY_BASELINE=/path/to/recovered-full-image.bin \
WATCH_SHARED_SOURCE=/path/to/RiscRTE-Watch-git-repository \
WATCH_SHARED_BUILD=/path/to/exact-shared-Home-build \
python -m unittest discover -s tests -p test_watch_shared_recovery.py -v
```

All 21 tests ran against the exact inputs locally. Without the three explicit
inputs, the six source-contract tests run and the 15 artifact tests are skipped;
such a run does not establish artifact qualification. The suite covers both
pair hashes, altered feature/dependency receipts, wrong source and bytes,
unrelated payload/authority changes, add/remove rejection, appdata/native/range
preservation, exact capacity failure, optional metadata semantics, and absence of
flashable outputs.

## Gates still open

1. Fit the exact shared Home and every selected provider in the immutable store
   while retaining every feature/font and at least two free blocks.
2. Select the required generic providers, with complete graph/instance closure,
   and preserve original retained-RGB565 app-sleep behavior.
3. Supply a qualified generic native successor or minimally additive profile
   build based on retained Runtime `06da76aa`, with exact native source/flags,
   runtime capacity and appdata/lifecycle behavior verified. No successor is
   selected by this checkpoint.
4. Run complete native/store admission normally and with ASan/UBSan, followed by
   actual device testing. Bind the new cohort/bank only after those build gates
   pass and preserve the factory appdata and all unrelated flash ranges.

Previously recovered firmware remains the qualified fallback. No publication,
release selection, flash, device instruction execution or physical test occurred.
