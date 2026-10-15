# Shared native UI integration: T-Watch 1.1.35

The final shared System source is `f31f89636304d202c49884e2e9b2e0b2ec5fb891`.
Release asset publication is authorized but remains gated on final product
qualification. Version 1.1.34 remains reserved
for the independent provisioning work. No serial access, flashing or deployment
is performed by this route.

## Preserved baseline

The exact latest published T-Watch product is `test-t064-crash-1.1.33`, source
`6eb69c44953752391e40c14b07d8833365d9cea7`. Its 16 MiB factory image has SHA-256
`077676642f2a3e938cf6fea497e6322dad198e1c2e98236d9367fb6bb5dcefca`.
The 121 store files include 59 ELFs. Home, clock faces, settings, preferences,
crash reports, Wi-Fi, BLE, Files, keyboard, Spectrum, and all other applications
remain byte-identical. Source pins include the hash of every baseline file.
Only Springboard ELF/manifest and the firmware-bound cohort may change.

Home already declares `runtime.retained-wake@1`; boot policy already grants
instance 0. Preserve both files exactly. Do not apply Waveshare's missing-grant
repair to this already-correct product. NVS, AppData, partition layout, boot
registration and all provider manifests remain unchanged.

The original .33 Springboard is reproducible from System
`9dcb2bbef44853e533d980a658a814d2c787a4fa` and Watch bridges
`6e82fdcaec0b73ed700d2104cfb4d94f011c19d4`. Its verified SHA-256 is
`b5aa9d642d0f64de560a799dcb535a466c35357367a1ef1cbf3112b000174273`
(150,924 bytes). The candidate keeps every original deployment feature and adds
only `PORTABLE_STAGE_PROFILE` as an explicit app telemetry build delta.

## Native Runtime route

The shared Runtime pin is `54461e8a7f61b28600b8ec8dcaf27b12cd45e829`.
`native/shared-ui-profile/watch-expanded-profile.ini` is byte-for-byte the
released .33 source profile from Runtime
`26a54ff7769f7c9072a2a133790cd293b72abcba`. The new profile retains its settings,
file-source, sharing, radio-IQ, retained-wake, recovery, ABI3 and capacity flags.
It selects 64 trace records with the same 64 cumulative counters, and explicitly
identifies the existing expanded Watch IQ target for the shared post-build gate.
No Waveshare vendor display source or provisioning profile is selected.

Stage with `scripts/shared_native_ui.py native-stage --runtime <checkout>`.
Build in that runtime using the installed pinned PlatformIO/toolchain:
`PLATFORMIO_SETTING_ENABLE_TELEMETRY=No pio run -c watch-native-ui.ini -e watch-native-ui -j1`.
Keep PlatformIO telemetry disabled. The owner has authorized the build tool
network/metadata routes needed for this task. An interval of zero enables checks
on every run; it does not disable PlatformIO core-version maintenance.

## Required release gates

1. Freeze the same final shared System pin used by Waveshare 0.1.44, including
   native vectors, elapsed-time polling, fallback input and first-frame brightness.
2. Reproduce .33 Springboard, then compile candidate with exact original flags.
3. Pass 240x240 and 410x502 full-feature, lifecycle, sync/async, retained-image,
   slow-refresh and brightness tests. Run ASan/UBSan; disable only unsupported
   LeakSanitizer tracing in this host environment.
4. Verify full native Runtime/store admission for all 59 ELFs and the bounded
   recorder/IQ symbols. Preserve every non-Springboard store byte.
5. Pack/round-trip the complete store and bind cohort to exact new firmware.
6. Construct a preserving update from exact 1.1.33 and test source identity,
   interrupted writes, readback and unchanged NVS/AppData/partition bytes.
7. Only after final shared pins and product source commit are coordinated,
   package and publish the tested assets. Factory images erase saved data;
   source tests and target builds do not qualify physical hardware.

## E-ink applicability

The same capability-aware native renderer declines animation for slow-refresh,
high-latency or image-retaining displays, preserving static input geometry.
X4 .121 has its own paper Home closure, System
`09400a550562ca9568ac7ab664ba3222eeedf2c8`, and product
`3ac013bd21815bf18e42466b656dbc333665bf6b`. The RGB System branch does not contain
paper_clock.c and does not by itself update that product. Audit paper retained
wake classification, sparse timer wake, sleep ownership and driver boundaries
separately against the shared Runtime ABI. No e-ink UI migration or hardware
assumption is part of this Watch integration.

The exact .121 sparse X4 sleep client passed 143 scenarios x 2 brightness x 2
diagnostic profiles in normal and ASan/UBSan modes (572 each). The actual shared
paper adapter passed 12 wake-light cases across normal/sanitized runs: interactive
wake restores saved light, while timer/cold stay dark. Preserve this distinction;
do not transplant the RGB first-visible-frame brightness helper into paper Home.

`qualify_shared_native_ui.py` archives the final pinned shared System and runs
the full both-Watch geometry/features/fallback/input/brightness/custody matrix
without PlatformIO or native firmware builds. Final pin selection is required.
The authorized native target run passed on Runtime54461e8. Final source-pin
qualification remains a separate gate.
`test_shared_ui_preservation.py` models both active banks, staged and torn writes,
readback corruption and final-selector interruption with protected NVS/AppData
and active-pair bytes. Its flash images are software fixtures only.

`package_shared_native_ui.py` requires final immutable source, exact cohort and
firmware identity, full-store native admission, shared source qualification and
all 272 preservation/fault cases. It creates local factory, preserving-kit and
evidence artifacts with independently verified ZIP contents and checksums. It
has no network or hardware operations. Its factory constructor has also been
checked against the exact released .33 image and the candidate native/store
bytes: bootloader, partition table, NVS, AppData and unrelated regions match.

The release workflow first checks finalized pins. With finalized=false, it
performs no release build. With finalized=true and publication_enabled=false,
it builds and retains qualified CI artifacts only. The later coordinated
publication-enabled commit creates a new prerelease, never reuses a tag, and
verifies the exact source and downloaded asset checksums.
