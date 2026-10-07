# Complete recovery and trace test build

Delivered artifact SHA256:
`27a9b0c80600fae99ebe79f05f4e04d70dbb1decae4a89d7eeb05adcd08ca98c`

The 16 MiB BMA423 initial image is written at offset 0x0. It erases both banks,
NVS/settings, BLE bond keys, saved Wi-Fi credentials, alarms/Points and app-data.
It is not a preserving OTA. All 22 apps and earlier completed features remain.

This build includes HID transport error/packet ownership and teardown/reconnect
corrections, SDR 0.1.4 stopped-bank ownership and stage tracing, and Runtime
0.1.41 balanced modem/power-domain/PHY ownership. Focused regressions, sanitizers,
target compilation and package integrity passed; CI was not awaited for delivery.

Hardware follow-up passed the former hard-freeze point and completed capture
cleanup, but reported `rc=4 stage=5 ready=1 end=0 cleanup=1`. That is a copy-stage
sentinel rejection, not a valid IQ burst. The later stop-cursor correction is
tracked separately; this exact artifact must not be described as SDR-qualified.

The original Watch commit f939c99 and Runtime commit 4b6f00e are preserved in the
included Git bundles. Runtime's published equivalent is 4a0891fc and has the
identical tree, as recorded in native-source-provenance.json. Future CI uses the
published native revision. The exact assembly command and binary component
identities are retained alongside this note. No device operation, merge or
release publication was performed by these scripts.
