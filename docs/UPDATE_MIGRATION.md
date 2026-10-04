# Paired update development candidate

This is for the original/non-Plus T-Watch-S3 with **16 MiB flash and 8 MiB OPI PSRAM**.
It requires a deliberate, one-time **full 16 MiB USB reflash and repartition**.
The generated merged BIN starts at offset `0x0`.

**Back up first. The full image overwrites both banks, including the upper 8 MiB,
NVS, settings, saved Wi-Fi profile, Stopwatch, alarms/countdowns, and Points in
Time records.** Previous delivered 8 MiB images left the upper 8 MiB untouched;
this new layout does not. Keep a known-good USB image and recovery procedure.
No device operation, production release or release-index update is performed by
these build scripts.

| Region | Offset | Size |
|---|---:|---:|
| NVS | 0x9000 | 0x6000 |
| Runtime bank 0 | 0x10000 | 0x300000 |
| Store bank 0 | 0x310000 | 0x4f0000 |
| Runtime bank 1 | 0x800000 | 0x300000 |
| Store bank 1 | 0xb00000 | 0x4f0000 |
| OTA boot selection | 0xff0000 | 0x2000 |
| Paired store journal | 0xff2000 | 0x2000 |

The initial image seeds bank 0 as valid; bank 1 is erased. The running Runtime
slot chooses its corresponding store, so power loss never selects firmware and
store independently. A new bank remains pending until the actual default Clock
has started successfully, presented a frame, and explicitly acknowledged health.
A failed/unconfirmed boot rolls back using the verified SDK bootloader. Missing,
corrupt or incompatible stores fail closed; they are never formatted on boot.

## Firmware Update

This app can update the native Runtime using an explicit compatible OTA asset.
It preserves the current store byte-for-byte in the inactive bank. The published
Watch 1.0 merged USB image is **USB-only** and cannot be written to an OTA slot.
The current release index does not yet offer a compatible Runtime OTA asset, so
that entry must show USB-only/unavailable rather than pretend an update works.
A future immutable release must add the documented `firmware.ota` record with
`kind=runtime-image`, `layout=riscrte-paired-16m-v1`, `store_abi=1`, numeric Runtime
version, exact byte length, SHA256, and same-release immutable asset URL.

## App Store

Only updates to already installed, explicitly authorized applications are in
scope. One update changes its validated ELF and manifest in the inactive store;
all unrelated files, driver/board configuration, grants and native firmware are
preserved. There is no automatic driver replacement, privilege grant or new app
installation. Catalog versions are compared numerically. Downgrades, changed
requirements/paths/entrypoints, invalid ELF/ABI/imports, wrong hashes and partial
responses are rejected before activation.

Both apps use the saved Wi-Fi profile and an explicit foreground connection.
Review the selected update before confirming. Cancellation is supported before
selection; activation uncertainty becomes restart-only to avoid damaging the
possibly selected bank. Retained radio/TLS cleanup blocks unsafe exit or sleep.
No credentials are embedded in artifacts or test fixtures.

## Verification limits

The delivery report must contain all exact-source CI jobs, hosted component
hashes, ELF-to-BIN proof, all actual profile/common/SPIFFS store admissions, and
real default Clock execution on the final BIN's extracted store. Controlled
fault tests cover source-wired update services through native HTTP/bank logic,
power-cut recovery, invalid downloads and isolation. Their lowest TLS/flash/
SPIFFS/ESP-image-verification boundary is mocked. They do not establish actual
TLS handshakes, physical power-loss reliability, flash endurance, memory peaks,
battery life, wake behavior or successful target OTA execution on a watch.
