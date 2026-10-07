# Complete Watch 1.0.7 test image

The user-requested fast test build contains all 22 current apps, Clock 0.10.3,
automatic low-battery settings, alarm/Hybrid sleep fixes, IMU fixes, SDR 0.1.2,
HID 0.1.1, BLE sensor/telemetry providers, and the final Spectrum neural floor guard.
The exact dependency commits, file identity, component offsets and hashes are in
`provenance.json`.

This is a **16 MiB initial image at flash offset 0x0**. It overwrites both banks,
NVS/settings, saved Wi-Fi credentials, alarms/Points and app-data. It is not a
preserving OTA. Target: original/non-Plus T-Watch-S3, BMA423, 16 MiB flash/8 MiB OPI PSRAM.
Compilation and package integrity were checked. Additional regressions/CI were
intentionally skipped for the urgent delivery; hardware qualification is not claimed.

The delivered source identity is 7aacdb4cf14e941f9889ce4a8f5e1fe9a1841010.
The published source a8ed10cd6bee2772bfb662a6c3324e7576540547 has exactly the same
Git tree, 6bad13af16e2b23d1c464b42c89571b7e4ada6cd. Commit metadata differs because
the urgent local build preceded connector publication. The small Git bundle
preserves the exact original build commit and requires ancestor 8c1a4246.

`assemble_test.py` is the exact assembly command, retained unchanged for custody.
Its input paths identify the complete low-battery app artifact, compiled native
candidate, and prior complete store used only to retain unchanged files. It
verifies all app flags, native component hashes, partition bounds, boot metadata,
and the independent SPIFFS round trip before writing the full image. The prior
store was assembled locally at 8c1a4246 with `build_current_watch_cohort.py` from
the accepted 1.0.4 artifact and its exact native source. No accepted historical
artifact, source pin, or publisher acceptance was changed.
