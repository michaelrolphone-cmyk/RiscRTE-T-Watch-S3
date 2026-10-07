# Watch 1.0.7 accepted complete image

This release promotes the exact complete image for which the owner reported
“SDR works” on 2026-10-07. The image is not rebuilt or relabeled internally.
It contains all 22 accepted apps, 21 providers, and Runtime 0.1.41.

The decompressed image is 16,777,216 bytes, SHA-256
`b039468858ab3cb5d1b53d843257e0e034d0a0b661ddaf3b74b59670519b0b2b`.
It is an INITIAL image at flash offset 0x0. Flashing replaces the full 16 MiB,
including both banks, NVS/settings, Wi-Fi credentials, Bluetooth bonds, alarms,
Points, and app-data. This release publishes no preserving OTA route. Install
the complete image before using its independent app/provider releases; older
App Store clients do not enforce minimum Runtime metadata.

The existing 1.0.3 native bridge and its assets remain unchanged. Exact accepted
component versions, source commits and hashes remain in `acceptance.json` and
the source custody under `docs/consolidated-test-1.0.7-sdr-cursor`. The owner’s
SDR report does not separately qualify sustained HID reconnect behavior.

The publisher extracts every app, manifest, provider and deployment file from
this SHA-pinned image. Existing immutable driver packages are reused only after
ELF equality, semantic manifest equality, original release-record and live
tag/source/inventory checks. All new release assets are uploaded as drafts,
downloaded and verified before publication. The catalog is updated last with
a non-force compare-and-swap against the exact committed predecessor.

The dedicated workflow validates on the release PR and publishes only after
the authorized change is merged to the repository's current default branch.
It does not access or flash a device.
