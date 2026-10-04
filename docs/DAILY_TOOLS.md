# Shared daily tools: Watch 0.5.1

This bounded increment adds Calculator 0.1.0 and Stopwatch 0.1.0 from
RiscRTE-Utilities to Springboard 1.3.8. The apps are independently owned and built
in the shared Utilities repository. Watch supplies the deployment catalog,
existing shared rendering/input client and exact capability grants.

Calculator has a direct touch keypad for four operations, decimal entry, sign,
Backspace and Clear, with repeated equals. It uses immediate execution and six
fractional decimal digits, rounded to nearest with ties away from zero. Division
by zero and values outside ±999,999,999.999999 show errors. There is no floating
point or new runtime math export.

Stopwatch uses monotonic milliseconds while open, displaying centiseconds and
updating at most every 50 ms plus actual full-frame transport time. The existing
raw RTC calendar anchors the saved running record when Start is confirmed.
Return to Springboard/Clock and reopen the app to continue after an app handoff,
Light sleep or a reset-based Deep wake. Clock still owns the 60-second idle sleep
policy; leaving Stopwatch open does not itself invoke sleep.

## Stopwatch persistence and precision

The app has one explicit `storage.key-value@1` grant, namespace instance 2 and
key `stopwatch`; Settings/Clock retain instance 1. The record is a versioned
20-byte app-owned encoding with validation/checksum. Start, Pause and confirmed
Reset are the only write actions, including explicit retries. There are no
heartbeat writes. Reset requires a second tap.

A running record restored from the RTC is visibly approximate: the RTC has only
whole-second resolution. Each recovered interval can add approximately one
second of uncertainty, which can accumulate across repeated recoveries. A paused
saved value is retained at its existing precision. Live display centiseconds
after recovery do not remove that earlier uncertainty. Clock edits while the
app is closed can change the recovered duration; a backward calendar before the
saved anchor is rejected. During one awake invocation, discrepancies beyond the
bounded two-second check freeze the trusted elapsed value and require Save Pause
or Reset. Small RTC edits inside that tolerance cannot be detected.

Missing state starts at zero. Corrupt/unsupported data requires explicit Reset
rather than silent replacement. Failed writes are unconfirmed, re-read where
possible, and never claim rollback. A failed Save Pause after an RTC anomaly
keeps the trustworthy awake value frozen instead of reconstructing through a
known-bad RTC. Saved state is not guaranteed across power loss, NVS failure or
full merged reflashing; the supplied 0x0 image overwrites the lower 8 MiB,
including NVS. Upper 8 MiB remains untouched.

## Preserved paths and verification

Runtime 0.1.5 and the same seven physical drivers are reused unchanged. No GPIO,
I2C, RTC, panel rendering/transport, PMU rail, touch transform, sleep mechanism,
font asset, Settings or Battery implementation changes are included. New apps
return to Springboard with touch/crown Back; Springboard returns to normal Clock.
Only Springboard links the expanded catalog. Existing Battery/Settings retain
the original catalog and their exact accepted bytes.

The strict baseline compares all 24 delivered 0.5.0 store files: 19 are unchanged;
5 are the boot catalog/grants, two Clock version manifests, Springboard ELF and
its version manifest. Four new Calculator/Stopwatch ELF/manifests bring the store
to 28. The default/normal Clock ELF bytes remain unchanged. Source hashes also
protect every existing driver, SDK, clock rendering and lifecycle source.

Verification includes deterministic arithmetic/state properties and failure
fixtures, real Runtime loading real shared apps and seven driver modules,
physical-transport frame assertions, reset-based persisted recovery, original
GUI/sleep regressions, target ELF/import validation, all eight variant stores,
common-store byte comparison and SPIFFS unpacking. Final delivery must come from
exact-head pinned GCC 8.4 CI and complete merged-image custody. Host/target tests
do not qualify the physical RTC accuracy, wake reliability, touch or current draw.

Countdown, scheduled alarm wake, vibration/sound settings and Timecard remain
separate authorized work. This image adds no awake-only substitute alarm, new
ULP program, double-tap gesture, Flashlight, Level or Steps app.
