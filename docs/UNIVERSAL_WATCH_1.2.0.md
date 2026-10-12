# T-Watch 1.2.0: shared Home integration candidate

This candidate replaces device-local Home with canonical RiscRTE-Watch 0.15.0.
It preserves all 25 applications and all 31 existing provider instances from
**delivered T-Watch 1.1.17**, including its shared Wi-Fi keyboard, Files, SDR,
Contexts, Points, alarms and wake fixes. Three independent generic power
service adapters bring the store to 34 providers / 58 distinct ELFs.

The application requests `board.battery`, `input.power-key`, `power.sleep`,
`display.output` and `display.power` independently. T-Watch-specific electrical
behavior stays in the existing physical drivers. Their legacy interfaces remain
available to unchanged applications. No application lookup uses an X4, LilyGO
or Waveshare capability name.

`default.elf` is the same compiled Home binary selected by the Waveshare 0.1.1
composition. `clock.elf` is the same 1,232-byte return module in both products,
not a second full Home implementation. The shared stager preserves original
namespace/shared-file selections, application IDs and all unrelated file bytes.

## Native and filesystem

The pinned common Runtime 0.3.2 supports 40 providers, 32 policy/requirement rows,
and the existing TCP/entropy/IQ services. `profiles/universal-native.ini` retains
T-Watch's native crown recovery binding and performance tracing. The bootloader
and partition table match the delivered 1.1.17 layout byte-for-byte. Native code
is replaced only within app0; app-data and unrelated flash regions are preserved
in the composed image. New cohort and bank hashes bind the new native/store pair.

The complete store retains eight empty SPIFFS blocks (32 KiB), including the
existing minimum free-block reserve. The change does not obtain space by removing
apps. Filesystem image decoding is checked independently after assembly.

## Build

Use the pinned Runtime `5323d1e834bdcc8e5e9fb0e8f76c383e46626801`, shared Home
`76aa47728192531ca9812f3e026057e0b174cb00`, and Drivers
`422e1e81a498fb6bdab9abf086325afc05a532dc`. CI builds the native profile, shared
app pair and generic adapters. Then provide the delivered baseline image:

```sh
python scripts/assemble_watch_universal.py \
  --baseline-image WATCH-1.1.17-FULL-INITIAL-ERASES-DATA.bin \
  --shared-source ../RiscRTE-Watch --shared-apps ../shared-build \
  --generic-power ../shared-build/generic-power \
  --runtime ../RiscRTE --native ../native-build --output build/watch-1.2.0
```

The shared build directory includes its `COMMIT.txt` and `build.json`. The native
directory includes `firmware.elf`, `firmware.bin`, `bootloader.bin`, `partitions.bin`
and `universal-native.ini`. Offline source archives use `--source-revision` and
`UNIVERSAL_RUNTIME_SOURCE_ARCHIVE` for the exact recorded public source snapshot;
source comparison remains enabled, not bypassed.

The full BIN is written only after ordinary and ASan/UBSan admission of the
complete store against the real native exports/ELF validator. Wrong native
BIN/ELF pairs, missing power providers, malformed Home and return modules, wrong
predecessors and incorrect capacity profiles are rejected. No target instruction
execution or physical I/O occurs in those admission tests.

## Hardware testing

**This is a full initial 16 MiB image at 0x0. Flashing it overwrites settings,
Wi-Fi credentials and application data. It is not a preserving update or OTA
package, despite preserving baseline regions during image composition.**

The candidate has not been physically tested. Check cold boot, face selection,
Springboard and return navigation, Wi-Fi keyboard, sleep/wake/crown, alarms,
Points/Contexts and SDR capture. Capture USB logs from power-on. Existing
first-frame and sleep diagnostics remain enabled. Do not treat component and
host validation as proof of power consumption, radio behavior or hardware boot.

Waveshare remains a smaller bring-up product; this increment establishes common
Home consumption and device-owned composition, not complete two-device feature
parity or rectangular UI reflow. The previously delivered binaries remain the
fallbacks; no accepted/stable release selection is changed.
