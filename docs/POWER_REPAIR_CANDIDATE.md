> Historical 1.0.10 lineage. The active 1.0.11 cutoff staging workflow is in
> [CUTOFF_2026_10_07.md](CUTOFF_2026_10_07.md); delivered 1.0.10 stays unchanged.

# Watch 1.0.10 power-repair test candidate

This is an explicit complete 22-application **test candidate**, retaining the
RF 1.0.8 feature profile and adding the current Watch sleep lifecycle repairs
with newly compiled Runtime 0.1.53. It is not a release or hardware acceptance.
Watch 1.0.9 belongs to separate provisioning work and is not used here.

## Current checkpoint and honest gates

The verified public Runtime source is
`3fde7198deffd21b263666a86f58eab2c6eadbc7`, with the exact source tree
`c8024f81179b68d8378ebccccc4e70a8ac2ce2ff` previously validated at local checkpoint
`efad74689fb235969ec705373621133736c94a36`. Final candidates must be freshly
rebuilt against that public source identity; provisional local artifacts are
not relabelled. The Watch repair source was published at `539b4221463d3626e3821f05e6f829d1d4c2d57e` with the
same tree as local repair checkpoint `cafdc280dde246dc76c6900d6026b9ceb007eb14`.
The complete app records bind the later clean profile source checkpoint.

Live read-only reservation checks on 2026-10-07 found no Watch product
`firmware-v1.0.10` tag or matching 1.0.10 issue, PR, or branch. The unrelated
historical `app-battery-v1.0.10` tag is not a product-version collision. These
checks do not create a reservation or authorize publication.

A source pin is mandatory. Pending pins, dirty or untracked source inputs,
stale native version/source markers, altered partitions, missing RF features,
old app versions, and modified accepted inputs fail closed. Existing accepted
1.0.7 and completed RF 1.0.8 custody code/descriptors remain unchanged.

## Exact input and versions

The delivered `rf-apps.zip` is bound to 10,451,352 bytes and SHA-256
`fad1e9dcadd862b6f1c14753253010ae61f85fbe896dbeb1c20e87fb4fb28339`, from Watch
`273b58d64ccc9a7dd66f0659271a942f244edcdf`. It supplies immutable original
catalog, board, boot-policy and manifest authoring inputs. It is not relabelled
as a new target build. Every application is freshly compiled with an incremented
deployment version, including Default/Clock 0.10.5 and Waterfall 0.2.1.

Source pins and every app version are in `apps/power-repair-sources.json`.
System Apps, Utilities, Productivity, and shared RF/BLE driver sources stay at
the completed RF pins. The candidate explicitly supplies PMU 0.6.2,
Panel 0.4.2, and IMU 0.4.2. The new profile is the only current-app overlay that
adds the panel binary; other profiles retain their original inventory.

The RF key-value API2 namespace 13 and app-data namespace 3 retain their exact
quota and authority. All 22 apps, 22 selected provider instances, existing
namespace owners, alarm/Points behavior, low-battery behavior, radio features,
source licenses, and RF float-division compatibility input remain required.

## Build the two application variants

Use the pinned ESP32-S3 GCC 8.4.0 toolchain and Python with pyelftools.
`RF_APPS` denotes the exact ZIP above, extracted from the delivered evidence.
`RUNTIME` must be clean at the explicitly reviewed Runtime 0.1.53 SHA.
Commit the reviewed descriptors and builder changes before starting a build.
When replacing a reviewed local source with its verified public same-tree SHA,
pass the exact old SHA through `--replace-reviewed-sha`; a different tree fails.

```sh
python scripts/pin_power_repair_sources.py --runtime "$RUNTIME" \
  --expected-sha REVIEWED_RUNTIME_SHA
# Review and commit the source pin and all builder/profile source files.
export TWATCH_CC=/path/to/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-gcc
for MODEL in bma423 bma456h; do
  python scripts/build_current_apps.py --profile power-repair \
    --system-apps "$SYSTEM" --utilities "$UTILITIES" \
    --productivity "$PRODUCTIVITY" --drivers "$DRIVERS" --runtime "$RUNTIME" \
    --baseline "$RF_APPS" --motion-model "$MODEL" --radio-model selectable \
    --output "dist/power-apps-$MODEL"
done
```

The builder rebuilds the Watch drivers, retains unmodified debug ELFs, verifies
compaction/imports/exports, records source and target-dependency hashes, and
checks the exact RF grants and features. The source profile does not weaken any
historical validator. A BMA456H candidate requires that exact hardware; no
physical sensor or radio-band inference is made by building it.

## Fresh native and complete stores

Produce Runtime's `esp32s3-16mb-appdata-iq` candidate using its own pinned build
and `scripts/paired_candidate.py --app-data --radio-iq` workflow. Pass that
fresh output as `NATIVE`. The Watch validator reruns ESP/ELF/partition, compiled
source/version/ABI, DRAM, TLS, rollback, radio-IQ and initial-appdata proofs.
It must contain Runtime 0.1.53, not relabelled accepted 0.1.41 bytes.

```sh
python scripts/build_power_watch_candidate.py build \
  --apps-dir dist/power-apps-bma423 --runtime "$RUNTIME" --native-dir "$NATIVE" \
  --mode both --installed-runtime "$ACCEPTED_RUNTIME" \
  --installed-native-dir "$ACCEPTED_NATIVE" --installed-system-apps "$ACCEPTED_SYSTEM" \
  --output dist/power-candidate-bma423
python scripts/build_power_watch_candidate.py build \
  --apps-dir dist/power-apps-bma456h --runtime "$RUNTIME" --native-dir "$NATIVE" \
  --mode initial --output dist/power-candidate-bma456h
```

Preserving mode requires the exact accepted Runtime 0.1.41 native custody,
including firmware SHA `776748a2331f6f6c5de0fc769bd13c8731c503a026217a767a18e86bac37dc3b`
and ELF SHA `426b85cdfd68b21a8acbbf20c489bed67b2b7f2b234549fb9944f4ff2518085f`.
A same-version rebuild with different bytes is rejected. It also requires
accepted System Apps `f146d82d4c2bc4d4b6ac97f7be83b04035ad7d60` and Runtime
`4a0891fc0ec10dcd100c6248768cabecaafec888` source checkouts.

The installed catalog parser proof is grammar-only. A private paired candidate
file is **not reachable through the currently installed updater catalog** until
separately approved release/catalog publication makes that exact file available.
Creating this local test artifact neither makes it installable from the current
catalog nor authorizes a release. Do not substitute a raw-flash operation.

The 31-scenario preserving host proof compiles both Runtime generations.
Installed-source writes/retries run the accepted 0.1.41 implementation;
candidate pending/healthy/rejected boots run the 0.1.53 implementation. Every
process result names its actual source and version. Exact target ELF graph
admission, namespace-theft and corruption negatives, failure/reboot/retry,
rollback requests, NVS and app-data sentinels, and previous-bank preservation
are required before the paired artifact appears.

Both modes independently round-trip the complete SPIFFS image and require at
least two free blocks. BMA423 is the only accepted preserving source geometry.
BMA456H initial-mode evidence cannot qualify a BMA423 preserving update.

## Verify and loader proof

```sh
python scripts/build_power_watch_candidate.py verify \
  --bundle dist/power-candidate-bma423 --runtime "$RUNTIME" --native-dir "$NATIVE" \
  --installed-runtime "$ACCEPTED_RUNTIME" --installed-native-dir "$ACCEPTED_NATIVE" \
  --installed-system-apps "$ACCEPTED_SYSTEM"
python scripts/check_power_loader_memory.py --runtime "$RUNTIME" \
  --utilities "$UTILITIES" --bin FULL_INITIAL_IMAGE --output dist/power-loader-bma423
```

Repeat the independent loader check for BMA456H. It executes the production
host allocation/relocation paths for all 43 ELF modules, fails both allocation
sites safely, tests eight allocator residues, checks PSRAM-only loading and
requires the conservative provider/app/frames subtotal to fit 4 MiB.

A paired payload contains native firmware followed by bootfs only and preserves
NVS/app-data. An explicitly named `FULL-INITIAL-ERASES-DATA` image is a separate
16 MiB, offset-zero destructive initial operation. Never flash a paired payload
at zero and never use the initial image as a preserving update.

Host proofs do not execute Xtensa instructions, real SPIFFS/TLS/flash, physical
sleep/wake/current measurements, or actual default-app health confirmation.
No device access, flashing, merge, release, or catalog update is performed.
