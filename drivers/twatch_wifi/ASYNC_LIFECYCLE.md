# Wi-Fi provider 0.2.1 asynchronous source checkpoint

This working source adds a complete size/tag/version-checked `wifi_async_v1`
suffix while preserving the full `wifi_api_v1` prefix. The matching native
Runtime must provide `garden_radio_async_v1`; older Runtime tables continue to
expose only the legacy provider table. This checkpoint is not a device-qualified
release.

`begin` copies its bounded request and returns an operation ID; `poll` returns
copied progress; `cancel` requests cooperative cleanup. PENDING/AGAIN/BUSY must
not be treated as cleanup failure or as success. Only IDLE plus quiescent permits
release. CLEANUP_FAILED/RETAINED preserves native ownership and mappings.
Neither provider nor native worker retains application pointers or callbacks.

The suffix also contains `service_begin`/`service_end`. Callers wrap a direct
synchronous provider service with the exact returned lease token and finish in
the same owner turn, without waiting or yielding. BUSY means defer the service
without invoking it. The native owner lease is reentrant for nested storage.

BLE enable/disable, broadcast lifecycle, and last-grant release are deferred
for the whole nonquiescent Wi-Fi operation, including connected/results phases.
This conservative bool-lifecycle limitation must be honored by the shared UI.
Existing bounded HCI RX/TX remains available.

Production cross-layer host tests are maintained with the native Runtime slice
in `test/run_radio_async_test.sh`, accepting `WATCH_SOURCE` to point at this
checkout. They compile this actual C provider, CpuPort, and production native
worker iteration with SDK-only shims and real host threads. Target RF, stop
stress, FreeRTOS stack watermarks and internal/PSRAM checks remain pending.

Source lineage: Wi-Fi 0.2.0 on Watch main at
`db5f6c5ba1a71ed3fcc22ff29847397a050b7ee4`. Runtime integration is coordinated
for the combined 0.2.2 successor; this provider branch does not stamp Runtime.
