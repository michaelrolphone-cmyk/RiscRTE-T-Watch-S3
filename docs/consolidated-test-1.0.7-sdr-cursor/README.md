# Complete Watch SDR cursor test image

The owner reported “SDR works” for this complete 22-app image on 2026-10-07. The exact delivered BIN has SHA-256 b039468858ab3cb5d1b53d843257e0e034d0a0b661ddaf3b74b59670519b0b2b, size 16,777,216 bytes, and embeds cohort 1.0.7 with Runtime 0.1.41. This records SDR acceptance, not an additional claim of sustained HID connection qualification.

The image includes all completed Spectrum neural, BLE HID/sensor/telemetry, automatic low-battery, alarm/Hybrid sleep, IMU and SDR work. It snapshots the live dump cursor before STOP and locates the committed sentinel boundary after stop/settle, so a hardware cursor reset cannot select an unwritten ring window. The regression reproduces the observed rc=4/stage=5/ready=1/end=0 failure and exercises delayed commit and wrap.

This is an INITIAL 16 MiB image at offset 0x0. Flashing it erases NVS, settings, Wi-Fi credentials, Bluetooth bonds, alarms, Points, app-data and both firmware/store banks. It is not a preserving OTA. No release/tag/catalog is published by these records.

`provenance.json` and `assemble_test.py` preserve the exact as-built inputs and assembly command. Their pre-delivery validation wording is historical; `source-and-acceptance.json` records the subsequent hardware report. The original local commit is retained in the verified Git bundle. Connector publication produced a different commit ID with an identical source tree; the delivered bytes are unchanged.
