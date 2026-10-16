# Watch 1.1.11 deep-wake test build

This focused successor of delivered 1.1.10 replaces only native Runtime with
qualified commit 391153360ba292604d70925741bad3be6e3d1e28. All 25 applications,
30 providers, Files 1.5.30, manifests, permissions and UI payloads are preserved
byte-for-byte. Only cohort identity, native firmware and derived image records
change.

Three reproduced native defects are repaired: a clean crown-monitor pause
refusal no longer leaves the prepared display permanently dark; acknowledged
pending or held crown events refuse deep entry; a crown gesture spanning deep
wake cannot be delivered again as a new sleep/navigation action. The native
GPIO21 polarity/RTC pull-up and PMIC power/charge policies remain unchanged.

Exact native target and host/sanitized regressions passed in the pinned source
recipe. Full-image admission is a separate required check. The reported physical
wake lockup still needs confirmation on the watch; this is not a battery-life
or hardware-qualified release.

Delivery is a raw full-initial BIN. Flashing at 0x0 erases internal settings,
saved Wi-Fi credentials and app data. A data-preserving update is not qualified.
Matching native and unchanged app symbols are retained separately.
