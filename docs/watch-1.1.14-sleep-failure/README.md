# Watch 1.1.14 sleep-acquisition failure identification

This focused successor preserves genuine sleep-refusal notices. It does not add
success/status notices to the watch face or change its normal design.

The previous `SLEEP ACQUIRE 0` label conflated three early refusal paths:
missing runtime acquisition API, failure to acquire settings namespace 1, and
failure to acquire motion.accel instance 7. The zero was initialized diagnostic
state, not a meaningful result from these boolean acquisition functions. These
paths now show `SLEEP ERR RUNTIME`, `SLEEP ERR SETTINGS`, or `SLEEP ERR MOTION`.
Other sleep stages retain their signed details. Bounded off-face diagnostics
record the capability and instance that could not be acquired.

The refusal and restoration behavior is unchanged. A refused sleep attempt has
not entered either light or deep sleep. Settings acquisition, enabled tap-wake
sensor acquisition, cleanup, alarm reconciliation, and all previous wake timing
changes are preserved. Tap wake is not disabled to conceal an acquisition error.

Controlled host failures reproduce both old ambiguous acquisition paths. They
do not establish which occurred on the physical watch: unavailable grants,
provider start failures, resource pressure, and device/I2C faults require actual
failure evidence. This release improves identification and does not claim the
unobserved device-side cause is repaired.

There is one Clock implementation: default.elf. The unchanged 1,232-byte
clock.elf is an empty return shim. Runtime unmaps it and starts a fresh default
invocation after Settings/app return, so the same diagnostic improvement covers
fresh boot and return-to-Clock without duplicating its implementation.

## Qualification

The focused tests use production Clock rendering across all 34 faces, repeated
acquisition refusals followed by successful sleep/wake, signed-result boundaries,
absent diagnostic callbacks, and the existing fast-wake cases. The normal face
is unchanged outside the existing error strip during refusals; successful wake
clears the error. Normal and ASan/UBSan results are retained with the image.

The target builder first reproduces the delivered Clock 0.11.4 byte-for-byte,
then compiles Clock 0.11.5. It checks all 98 source dependency bytes and permits
only crown.c and watch_motion_client.h to differ. Imports/exports and capability
grants remain unchanged. Native Runtime 267aab6, its matching symbols, and every
other application/provider are byte-preserved from Watch 1.1.13.

The assembler validates the complete 54-ELF cohort using the exact native source,
normal and ASan/UBSan. Only default.elf, default.json and cohort.json change in
the store. Build-time checks add no device-side file scan or checksum.

Physical sleep/wake and the next reported acquisition error still need testing.
For sleep-mode verification, TERMINAL face uptime continuing rules out a deep
reset. Restarted uptime needs retained `diag` boot detail=8 to distinguish deep
wake from another reset; fast wake alone is not proof of sleep mode.

## Flashing

The 16 MiB full initial BIN starts at flash offset zero and erases internal data
and settings. No data-preserving update is qualified. Source recipe, native and
Clock symbols, and complete admission receipts accompany the retained evidence.
