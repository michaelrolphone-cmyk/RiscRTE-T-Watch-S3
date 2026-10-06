# Current Watch application cohort

`apps/current-apps-sources.json` selects the exact Runtime, System, Utilities and
Productivity sources. These can be coordinated PR heads; they are not assumed
to be merged. Historical update/audio/Points inputs remain frozen custody
inputs. The current package contains 19 applications, 17 selected provider
instances and 17 visible launcher entries. Two I2C instances share one provider
ELF, so the final 72-file store contains 35 unique ELFs.

The cohort adds File Browser, the BLE sensor scanner, LoRa Messages with an
explicit hardware picker, Spectrum 0.4.1 temporal examples and Monitor context and Timecard 0.1.0.
Timecard keeps the authoritative model at version 1.0.4. Existing Quick Controls,
alarms/Points, clock faces, Wi-Fi, updates and double-tap sleep/wake remain part
of the same source profile. Physical radio, motion wake and storage behavior
remain unqualified by these software tests.

## Explicit app-data layout

Only the opt-in `esp32s3-16mb-appdata` target uses
`riscrte-paired-appdata-v2` / store ABI2:

| Region | Offset | Bytes |
|---|---:|---:|
| app0 | 0x10000 | 0x260000 |
| appdata | 0x270000 | 0x80000 |
| bootfs0 | 0x2f0000 | 0x510000 |
| app1 | 0x800000 | 0x260000 |
| reserved | 0xa60000 | 0x80000 |
| bootfs1 | 0xae0000 | 0x510000 |
| otadata | 0xff0000 | 0x2000 |
| bank_state | 0xff2000 | 0x2000 |

NVS remains at 0x9000/0x6000. Both legacy ABI1 builds and their partition map
remain separate and unchanged. The initial full 16 MiB BIN replaces both banks,
NVS and application data. No data-preserving repartition/migration is supplied.
The verified empty disk2.1 image belongs only to initial provisioning; ordinary
paired OTA never includes it. Old firmware cannot admit the ABI2 OTA marker.
The native mount refuses a missing or mismatched partition and disables format
and grow operations.

The measured complete store has 3,845,523 file payload bytes. The pinned packer
cannot fit it in 0x4f0000 or 0x500000; 0x510000 passes pack/unpack and independent
read-only decoding. Provider ELFs remain unchanged. Application-only compaction
retains full original debug ELFs and verifies loader-relevant semantics. Every
final build must pack the actual complete store again; payload size alone is
not a capacity guarantee. The measured native BIN is 1,193,872 bytes, leaving
1,296,496 bytes in its slot; later source pins must remeasure that headroom.

## Authority and persistence

Spectrum 0.4.1 keeps room identification on its raw learned-room path and surfaces it in Monitor while preserving RAW/AUTO/MANUAL filtering. Detected temporal events and active frequency labels are ranked by detector confidence with canonical amplitude.\n\nTimecard receives `storage.app-data@1` namespace1. Spectrum receives namespace2,
retaining `storage.key-value@2` namespace7 and the separate preference namespace1
at API1. Spectrum uses all 12 requirement/grant slots. Timecard's source navigation
requirement is explicitly materialized by the Watch's existing local crown path
and battery capability; its generated profile has 10 requirement/grant entries.
No app receives an unscoped filesystem or a writable boot store.

Each app-data namespace supports at most four files and 128 KiB committed bytes,
with a 64 KiB maximum file and bounded atomic staging. This is a limit, not a
reservation of physical free space. Retained-close failures block further I/O
and handoff until restart. Timecard and Spectrum owner tests exercise their real
filesystem consumers, uncertain writes, retries and cleanup. Watch admission
and Clock fixtures separately prove that startup does not perform app-data I/O.

The LoRa picker requires an explicit choice matching the installed radio. It
cannot change a radio's physical band. Selecting a profile does not configure,
receive or transmit on the selectable provider; Listen/Send does that after RF
validation. An unknown legacy profile stays unselected. BLE scanning is passive
advertising only. File Browser previews admitted installed files read-only.

## Build and verification

Build from clean checkouts at the configured source pins:

```
TWATCH_CC=/path/to/xtensa-esp32s3-elf-gcc python3 scripts/build_current_apps.py \
  --motion-model bma423 --radio-model selectable \
  --system-apps /sources/system-apps --utilities /sources/utilities \
  --productivity /sources/productivity --runtime /sources/runtime \
  --baseline /artifacts/audio-tools-common.zip --output /output/current-apps
```

Use the BMA423 profile for the owner's confirmed base S3. The separately compiled
BMA456H profile requires matching hardware; software compilation is not physical
chip identification or wake qualification. The five-minute Hybrid wake problem
remains outside this increment. No sleep serial capture is required.

The output must be empty. Historical custody is verified before applying the
current payload. Every app/provider has strict target structure, entry and
import validation. New launcher glyphs come from the exact System font subset.
The canonical ZIP records source hashes, profiles and full/compacted hashes;
`debug/` retains the original application ELFs outside the installable store.

Build/freeze the Runtime with `scripts/paired_candidate.py --app-data` and the
verified initial image. Pass `--initialize-app-data`, the candidate directory and
`--current-apps-artifact-dir` to `scripts/build_latest_main_flash.py`. The full BIN
is explicitly classified as an initial app-data image. Its manifest records the
layout, exact pins, every store file, hashes and overwrite limits.

`check_current_loader_memory.py` accepts the actual `--bin` or `--image`. It runs
the selected Runtime's allocation/section functions, verifies PSRAM-only flags,
text/data allocation failures and cleanup, then executes the complete Xtensa
relocation path on the host without executing target instructions. Eight
allocator residues check mapped bytes and redzones. All 17 provider instances
are counted, including duplicate module instances. The measured loader/frame
subtotal is 3,559,671 bytes; its 4 MiB regression threshold leaves room for other
PSRAM use but is not a prediction of physical free heap. Native radio/audio
buffers, stack use, fragmentation and current draw still require hardware checks.

For the actual final store, run `scripts/test_current_apps_runtime.py` with the
four source directories, current artifact and `--bin` (or isolated `--image`).
Both normal and `SANITIZE=1 ADDRESS_SANITIZE=1 ASAN_OPTIONS=detect_leaks=0` lanes
preserve every JSON policy and run real Runtime admission plus six Clock
startup/lifecycle scenarios with host-architecture module substitutions.
Historical lanes continue independently. CI rebuilds both sensor variants,
freezes both native layouts, checks final loader memory and executes both final
stores. No CI step accesses or flashes a device.
