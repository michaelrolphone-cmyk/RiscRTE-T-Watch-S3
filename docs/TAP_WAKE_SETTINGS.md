# Tap wake settings and measured calibration

Software increment after released Watch 1.0.2: IMU 0.4.0 and Settings 1.3.0.
Physical qualification is pending. No new BIN is delivered by this change.
The release's working crown path and idle/APS reset preconditions are retained.

## Off and persistence

Settings → Tap to Wake has explicit Off, On, Calibrate, Cancel and Save controls.
The existing namespace-1 `storage.key-value@1` grant holds one eight-byte
versioned/CRC-checked `tap_wake` record. It contains the enable flag, separate
BMA423/BMA456H encoded settings, and per-profile measured flags. There are no
new native exports, runtime settings, storage partitions, or seeded defaults.
Paired updates preserve this existing NVS namespace.

A missing record retains released behavior: On, BMA423 sensitivity 3, and
BMA456H threshold scale 12. A malformed or unreadable record selects crown/timer
wake only with a diagnostic. A failed storage acquisition/refused cleanup blocks
that sleep attempt. Off is checked before acquiring the IMU: every current app
uses the crown/alarm-only adapter, including Light, Deep and Hybrid. The normal
one-minute inactivity policy and alarm reconciliation remain unchanged.

Save performs one write and an exact readback. A failed write/readback is shown
as unconfirmed, because persistence may have occurred. Cancel never writes.
Calibration while Off leaves Off selected. Changing either sensor profile does
not discard the other profile's value or measured flag.

## What is measured

The app opens an explicit awake observation session on the existing
`motion.accel@1` capability. Its append-only suffix describes the actual sensor's
encoded parameter range, accepts a candidate value, and reports the real Bosch
double-tap interrupt plus fresh acceleration samples. The driver configures and
reads back the actual matching feature engine. Samples use the configured ±2 g
range and the correct BMA423 12-bit/BMA456H 16-bit resolution. A pinned BMA423
library difference requires explicitly initializing its software XYZ map;
otherwise that library reads X into all three output axes. This is covered by
signed, distinct-axis regression samples.

Calibration starts at the least-sensitive supported value (7 or 15). At each
candidate it waits 1.5 seconds after setup, prompts for three deliberate pairs
in separate trials, and measures an actual hardware double-tap result in each
five-second trial. Each detected pair is followed by a one-second window with
no further detector events. A missed trial moves one encoded step toward more
sensitive and restarts all three trials. No candidate is saved because it was
merely proposed or because a timeout occurred.

After three successful trials, the app asks for five seconds of ordinary worn
wrist movement without deliberate taps. It requires no double-tap events,
25 or more fresh samples, and at least 150 mg of observed axis span. That span
is only a check that the movement trial actually contained movement. It is not
an acceleration-to-sensitivity conversion or a tap force threshold. Delayed,
stalled, absent, failed or noisy observations cannot produce a measured result.
The first candidate that passes is the least-sensitive *tested* value with three
successful detections and no triggers in that movement trial.

The sensor is restored and its ownership released before Save becomes available.
A cancelled, noisy, insufficient, interrupted or failed session does not alter
saved preferences. Restore failure retains the enrollment and grant; the page
provides a Retry Restore action. Exit cannot release an unrestored sensor.
Long active calibration suppresses app idle sleep and starts a fresh inactivity
interval when it ends. Held Save contacts cannot cause repeated commits.

## Important limits

This is an empirical hardware-detector calibration, not a physical-force model.
It does not translate Bosch's encoded sensitivity into g, infer unsampled impact
peaks, or promise a false-wake rate from a short trial. The UI asks for similar
substantial knocks, but the autonomous hardware still decides double taps.
Strict equality of the two impact magnitudes and a post-pair quiet condition are
not newly enforced during Deep sleep. The existing Deep boot resets the sensor
and does not retain the original impacts for a custom sample classifier. The
awake calibration's quiet and movement checks do not remove that limitation.

No hardware qualification, battery-current measurement, usability calibration,
or reliable pickup/tilt-rejection claim is made from host or target tests.

## Review and verification

- `scripts/test_motion_wake.py`: actual pinned Bosch source/config images, both
  sensors, all 24 encoded values, distinct signed sample axes, status ack only
  in observation sessions, every preparation/restore transfer fault, every
  observation transfer fault, stale/held interrupts and retained cleanup.
- `scripts/test_alarm_integration.py`: saved Off bypasses the IMU in all sleep
  modes, both profile settings, crown/alarm behavior, corrupt/unavailable
  records, short ABI, acquisition, release, and retained cleanup.
- System `scripts/test_tap_settings.py`: production Nova controller/rendering,
  both sensor profiles and orientations, normal and ASan/UBSan executions;
  cancellation, read/setup/restore failures, noise, stale/missing samples,
  uncertain writes, held Save, Off calibration and >60-second sessions.
- System `scripts/test_nova_settings.py`: existing 272 controller executions.
- Pinned Xtensa 8.4.0 builds validate driver and Settings ELF layouts/imports.
- System `docs/nova/tap-wake/calibration-contact-sheet.png` shows production UI
  rendered with modeled peripherals. It is not a device screenshot.

Before hardware qualification: exercise Off/On across Light, Deep and Hybrid;
restart and update with Off and each measured value saved; try cancellation and
repeated calibration; compare deliberate pairs, single knocks, pickup, tilt,
walking and ordinary wrist movement; verify crown and due alarms throughout.
