# Adopted T-Watch recovery baseline

The existing `T-Watch-S3-1.1.21-r1-AppData-Fix-full-0x0.bin` is the retained
baseline. Its SHA-256 is
`4e43fc376021779a2d7a5cada96aee255735d5db1eb0e896c5aacf65bb3889bc`.
This checkpoint does not make or deliver a replacement build. This is LilyGO
T-Watch S3, not Waveshare, and has no SD card.

## Exact lineage

- Home and all 55 app/provider ELFs are unchanged from delivered Watch 1.1.20.
  The Home source is `b7a6cf0d2505ecf9b1c625bbfcc6d4048c13b471`; swipe sampling,
  ordered replay, RTC reconciliation, Points, fonts and cumulative app repairs
  remain present. The prior receipt head is `5ded35434efb4830ce20fc842fb82bf968f87908`.
- Native source is public Runtime `06da76aa7f074220b74a282badca0ed0061f1643`,
  a direct child of retained `64c8e52e46fd91e8fdafd636db04eed88f0c51a9`.
  Only `CpuPort.cpp` changes: the scoped GPIO pad-hold fix already in Runtime PR73.
  The exact tree is `4ac49c9bd869dd4a1e87b9e135b8cda2d3425fbb`.
- [Successful native build](https://github.com/michaelrolphone-cmyk/RiscRTE/actions/runs/38330769241)
  used `pio run -c watch-file-source-profile.ini -e watch-file-source -j 1`.
  Its logged native BIN SHA matches the recovered image; see `selection.json`.
- The stored cohort's `source_revision` is the **assembly recipe**
  `eab404c6b17ef3da8f68b991e90e5be06a724a96`, not the native source. The assembly
  helper at that revision updates native firmware, cohort metadata and paired
  bank hashes, preserving every other app/provider byte. The later r1 repack
  changes only appdata, at `0x270000`, size `0x80000`.
- `selection.json` binds all 113 store files, native image, paired metadata,
  partition table and full image. `image-audit.json` independently verifies the
  preserved cohort and two completely free SPIFFS blocks.

## Packaging defect and correction

Watch 1.1.20 and the first 1.1.21 package left appdata entirely erased. Runtime
deliberately refuses boot-time formatting. The missing mounted file-source
backend prevented manifest admission before Home could start. The r1 package
supplies an empty LittleFS disk 2.1 filesystem generated from exact source.
Do not enable automatic formatting to conceal packaging errors.

The source-pinned formatter already exists in recovered Runtime at
`scripts/app_data_image.py` and `scripts/app_data_format.c`. It uses LittleFS
`f53a0cc961a8acac85f868b431d2f3e58e447ba3`, verifies the four source hashes,
formats and remounts an empty filesystem, and produces the deterministic
appdata SHA `5f03c248f2de31c4da9ae8d9bc2033df064cee5e37694a9982f70fbb2f1d2ef0`.
No native shared source is changed by this Watch checkpoint.

## Reproduction and admission

Use the exact source/profile and delivered 1.1.20 predecessor with Runtime's
`assemble_display_recovery.py` at the assembly recipe above for the original
1.1.21 recovery. Then generate and package appdata using:

```sh
python scripts/watch_factory_appdata.py format --runtime RECOVERED_RUNTIME \
  --littlefs-source PINNED_LITTLEFS --output EMPTY_APPDATA
python scripts/watch_factory_appdata.py pack --runtime RECOVERED_RUNTIME \
  --appdata EMPTY_APPDATA --input ORIGINAL_1_1_21_FULL_BIN --output NEW_INITIAL_BIN
python scripts/watch_factory_appdata.py verify --image NEW_INITIAL_BIN
python scripts/verify_watch_recovery.py --image EXISTING_R1_BIN --previous DELIVERED_1_1_20_BIN
python scripts/test_watch_factory_appdata.py --appdata EMPTY_APPDATA/appdata.bin -v
```

The packer refuses a nonempty source partition, wrong geometry/checksum,
unqualified filesystem bytes and an existing destination. Only the appdata
range may change. Future initial-image recipes must run the partition-content
gate and production mount regression in addition to ELF/cohort admission.
The retained historical assemblers remain immutable provenance, not a safe
substitute for the recovered baseline.

Run `scripts/verify_factory_appdata_mount.py --runtime RECOVERED_RUNTIME
--old-image DELIVERED_1_1_20_BIN --recovered-image EXISTING_R1_BIN
--selection docs/watch-recovery/delivered-image-selection.json --output HOST_RESULTS`
for the exact delivered-image regression. `--vendor` optionally supplies already
hash-verified ESP LittleFS sources. CI instead uses explicitly nonbootable,
storage-only fixtures generated from the retained partition table and newly
reproduced filesystem; it does not claim to rebuild the delivered firmware.

**Full initial images at offset 0 overwrite settings, credentials, bonds and
application data. These tools are not data-preserving update/migration tools.**

## Test boundaries

The recovered evidence originally ran normal host production storage tests.
This checkpoint independently repeats normal and ASan/UBSan tests using exact
full-image bytes, real pinned LittleFS/ESP adapter and production AppData,
NativeAppDataMount and NativeFileSource. The old image fails with zero flash
program/erase calls; r1 mounts, reads back all 65,536 scratch bytes, and retains
saved AppData across a separate-process cold remount. Ordinary mount/FileSource
fault regressions also run. LeakSanitizer is disabled after a host fatal error
with a ptrace incompatibility hint; address and undefined checks remain enabled.

These are host flash/RTOS models, not Xtensa execution or optical display tests.
The owner separately reports both recovery builds working. No new hardware
test, flash, release, merge or duplicate delivery is claimed by this checkpoint.
