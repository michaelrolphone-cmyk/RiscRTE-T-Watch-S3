# Deep-wake stage timing checkpoint

Clock 0.11.4 adds bounded startup/wake diagnostics and reduces the provider
closure required before the first Clock frame. It does not claim a measured
deep-wake improvement. The user reported that
1.1.12 light wake was nearly immediate while deep wake still took about seven
seconds; no device timestamp capture is available in this checkpoint.

## Stage boundaries

`WATCH_WAKE` records retain boot-local `t_ms` and invocation/wake-local
`elapsed_ms`. The first foreground path now brackets:

1. Native realtime/retained-wake grants
2. Display activation, battery grant, RTC acquisition/seeding or deep deferral
3. Saved face/Quick settings and Points configuration
4. Touch acquisition
5. First render, completed transfer, and backlight unblank
6. The later sleep-setting lookup and first normal input poll
7. Alarm service acquisition/reconciliation before optional services or handoff

`first-frame` shares the timestamp sampled immediately after successful
unblank with `unblank-end`; it no longer includes the later sleep-setting read.
The rendering checkpoints run only on fresh entry or wake, never on every
foreground frame. Native health sampling is best-effort: a failed diagnostic
sample omits a record without changing application control flow. Fixed-size
stack buffers are used. No storage read, checksum, provider activation, heap
allocation, or persisted record is introduced for diagnostics.

Normal fresh entry emits 25 records through first input, then four alarm
records and the eight existing deferred-phase records. Valid deep entry adds
one `rtc-deferred` record. A light resume adds only the six render,
transfer, and unblank records to its existing wake/service records. A failed
operation leaves its begin record without a misleading successful end record.

## Read-only source findings

The delivered fast default has no old 1.8-second intro or 250 ms final hold.
Normal explicit provider startup waits are panel software-reset 150 ms,
panel sleep-out 120 ms, and PMU settling 5 ms. Alarm reconciliation performs
bounded cooperative steps; due occurrences can legitimately enter the alarm
foreground UI. These are not evidence of a fixed seven-second delay.

The delivered 1.1.12 normal pre-frame path needs ten provider instances: GPIO,
system/touch I2C, PMU, panel, RTC, haptic, speaker, alarm service, and touch.
Their ELF files total 66,504 bytes, in addition to the 858,772-byte default ELF.
The Clock ELF includes 755,172 bytes of read-only data. Its largest assets are
current face, calendar, Points, and Quick UI fonts/artwork; the disabled boot
effect is already discarded. Removing those assets would remove features or
require a separate lazy-asset design.

## Minimal Clock/input closure

For classified deep wake with a valid native realtime snapshot, fast Clock
does not acquire the external RTC merely to seed an already valid clock.
Cold/reset entry and unset native time retain the original RTC acquisition
and seeding behavior. The snapshot is validated by the existing Runtime
client, and a retained/context failure remains terminal.

Alarm service and its RTC, haptic, and speaker dependencies are admitted
immediately after the first settled Clock frame and first normal crown/touch
poll. No extra cosmetic frame or settling delay is inserted. Reconciliation
finishes before handling a queued sleep/navigation request or admitting
radios/Contexts. Due alarms still run the unchanged service reconciliation,
expiry, output, dismissal, and failure paths. A due alarm that cancels input
also cancels the crown event sampled before its admission. Its completed
presentation therefore cannot accidentally cause a second sleep action.
Light wake retains the already admitted service and its prior alarm-first
resume handling.

The deep pre-frame provider closure is now six instances / 34,796 ELF bytes:
GPIO, both I2C instances, PMU, panel, and touch. Cold entry adds RTC for seven
instances / 39,032 bytes. Battery remains mandatory because panel itself
depends on PMU. Runtime realtime/wake grants and selected-face/Points/Quick
settings are native services, not provider ELFs, and remain available before
the frame to preserve saved appearance and time policy. All capabilities and
features remain declared and available after admission.

Source locations: `apps/clock/crown.c`, `apps/clock/clock_alarm.inc`,
`apps/clock/launcher_touch.h`, `apps/runtime_features/clock_runtime.h`,
`drivers/twatch_panel/driver.c`, `drivers/twatch_pmu/driver.c`, and
`include/common/display.h`.

## Qualification

The production-source fast Clock host suite passes normally and with
AddressSanitizer/UndefinedBehaviorSanitizer. Added tests cover exact stage
ordering, first-frame before a deliberately slow sleep-setting read, failed
essential grants, failed frame acquisition/transfer/unblank, an unavailable
diagnostic sample, and bounded repeated-light-wake markers. Existing tests
continue to cover saved face/time/brightness, Points, due alarms, low battery,
navigation during transfer, radio policy, service failures, and retention.
The minimal-closure cases additionally assert no alarm acquisition before
first frame/input, no RTC acquisition on valid classified deep wake, RTC
fallback when native time is unset, a modeled 700 ms alarm-load cost entirely
after first input, due alarm delivery on deep wake, and cancellation of a
sampled pre-alert long crown event. The alarm service implementation and
its expiry policy are unchanged; host fixtures are not physical qualification.

The target builder reproduces the original non-fast default exactly, then
builds the fast Clock 0.11.4 with the same 98-input closure and unchanged
imports/exports/grants. Changed closure inputs are `apps/clock/crown.c` and
the fast-only input-cancel signal in `apps/clock/clock_alarm.inc`.
The new target is 860,156 bytes. Build receipt and symbols are retained in the
target output directory. These host and target checks are not hardware timing.
