# Later Watch 1.0.5 integration

This cohort combines the completed tap settings/calibration, read-only power screens, focused launcher, NOVA Frequency Generator and BLE HID controls. It remains separate from the frozen native bridge 1.0.3 and SDR 1.0.4 acceptance. Runtime 0.1.35 combines the preserved IQ/migration changes with retained sleep/reset diagnostics. The installed 0.1.34 source remains the upgrade-admission authority.

All current clients receive distinct component versions for the changed Watch-local tap/sleep adapter, including both Clock entrypoints 0.10.2. Settings alone enables PORTABLE_TAP_SETTINGS. Battery alone enables PORTABLE_POWER_STATUS and BATTERY_RETURN_APP so Details Back stays in the app. Frequency Generator enables NOVA while retaining adapter-owned Back. The launcher opts into 20 entries; the shared default remains 17. The two HID cards are appended after all existing catalog entries.

BLE Touchpad and BLE Buttons use the generic bluetooth.hid@1 Global0 provider. It consumes the unique HCI provider plus monotonic clock and exactly four bound keys in new private namespace 10: hid_ours, hid_peer, hid_ccc and hid_identity. Applications cannot read bond records. Only Buttons gets new private namespace 11. Their shared namespace 1 grants use a version-bound migration from the exact accepted 1.0.4 source 674729db to 1.0.5. Existing board declarations, grants and private owners remain unchanged.

The final build must pass exact-source target compilation, the actual 20-entry catalog against the production adapter, all 40 target ELF allocation/relocation checks, current Clock normal/sanitized lifecycle execution, and the one-stage installed-Runtime admission/rollback/persistence proof. The packaging helpers reject extra/private grants and hardware changes; they do not publish or operate a device.

Charging behavior, physical tap calibration, BLE interoperability/touch latency and real OTA/power-loss remain hardware qualification. PMU initialization reads and verifies inherited TS configuration; it does not rewrite it or establish that charging is repaired. Full initial images are destructive and are not an installed-Watch upgrade route.
