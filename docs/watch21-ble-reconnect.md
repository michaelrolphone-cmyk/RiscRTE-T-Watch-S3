# Watch 1.0.21 BLE reconnect test increment

This recipe replaces only BLE HID with qualified provider 0.1.4 on the exact delivered Watch 1.0.20 image. All 23 application ELFs, their manifests, native Runtime 0.1.73, boot policy, board selection, app-data initialization and partition layout are preserved. The provider manifest version and cohort identity change alongside the provider ELF.

The repair clears a stale poisoned latch only after the NimBLE host stopped, the connection disappeared and native controller release succeeded. It permits same-host reconnect and explicit Forget/new-host pairing after the reproduced disconnect-command race. Unsafe cleanup still retains ownership and cannot report successful Forget. Local production tests cover 34 scenarios, including cold restart, private addresses, persisted bonds and unrelated settings.

The full 16 MiB BIN is an initial installation: erase all flash, then write at address 0x0. It erases settings, bonds, saved events and training/model data. A paired payload is emitted for custody, but no preserving transaction or live feed is qualified by this recipe. No hardware result is claimed.

## Build and verification

Run `scripts/build_ble_reconnect_increment.py --help`. Supply the clean exact driver source recorded in `apps/ble-reconnect-121.json`, the canonical Runtime 0.1.73 source and candidate used by Watch 20, the exact delivered Watch 20 full BIN, its `LICENSES-baseline.zip`, and a new output directory. The recipe verifies all frozen inputs before writing output, compares all 95 store members, reconstructs and extracts the full image independently, and runs actual Runtime whole-store/cohort admission normally and with ASan/UBSan. LeakSanitizer is disabled under the traced executor.

`--verify-source <recipe-commit>` performs read-only input, output, inventory, source, license, native placement and partition custody checks. This does not run target machine instructions or perform a device action.
