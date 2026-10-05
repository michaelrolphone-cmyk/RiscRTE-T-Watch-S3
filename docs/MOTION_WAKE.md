# Motion-sensor double-tap wake

The current application cohort uses autonomous physical double taps in both
Light and Deep sleep. These are two knocks detected by the accelerometer, not
capacitive touch contacts. Crown wake and alarm timers remain available. The
one-minute idle policy and existing Hybrid transition are unchanged; this work
does not include the separate deferred Hybrid wake-recovery prototype.

## Hardware and explicit identity

The non-Plus T-Watch-S3 sensor is at system I2C address 0x19 on SDA10/SCL11.
INT1 connects to GPIO14; INT2 is unconnected. The inspected LILYGO schematic
page 4 shows VDD/VDDIO on +3V3, supplied by DC1 on page 1, and a fitted 10 kΩ R10
pulldown on INT1. R15 pullup is marked not fitted. Motion profiles therefore use
active-high push-pull INT1 with no MCU pullup. No rail is switched or reprogrammed.
Using active-low push-pull would hold the fitted resistor high during sleep,
adding approximately 0.33 mA at 3.3 V by calculation. This is not a measurement.

BMA423 (chip ID 0x13) and BMA456H (chip ID 0x16) remain separate explicit profiles.
The driver reads and compares the selected ID before any feature upload. There
is no default physical variant and no inferred selection from past boot success:
older stores did not load an IMU. Current builds require --motion-model bma423 or
--motion-model bma456h and record it. Confirm the installed part before selecting
an image. Both chips' source/register models are tested; neither is hardware
qualified by these tests.

## Driver and ownership

Pinned Bosch source/images are retained verbatim from SensorLib commit
477fc682e9ed30ced39774f3b7e93a1504968884. The source hash manifest is
vendor/SensorLib/PROVENANCE.json. BSD license and the original BMA423 notices
accompany the IMU package and current-image materials.

The IMU remains an independently mapped ELF using owned GPIO and I2C capabilities.
It enrolls its own input before any sleep mutation, snapshots its sample/IRQ
configuration, resets and loads the matching feature image, validates ASIC init,
and configures 200 Hz, 2 g, AVG2/CIC sampling. BMA423 explicitly selects double
rather than single tap. BMA456H enables only its double-tap feature; single,
triple, step, activity and motion features stay disabled. Only the selected tap
interrupt maps to INT1, in latched mode. A stale status is acknowledged before
enabling the feature. Subsequent pending checks do not acknowledge interrupts.

The line must be inactive before entry and after native wake arm. Held lines
refuse sleep instead of creating a reboot loop. Light wake or ordinary refusal
resets the feature engine, restores and reads back saved configuration, then
withdraws enrollment. Partial preparation and cleanup remain retryable. A sticky
transport-error latch prevents vendor upload loops from hiding an earlier failed
I2C transaction. Delays verify monotonic elapsed time with a quantization margin
and bounded yielding retries, including the required 450µs between low-power
writes; a stalled clock fails closed. Failed sensor rollback retains the enrollment and resources;
failed native rollback returns RETAINED and forbids further peripheral I/O.
Deep success never returns, and a fresh boot resets/reinitializes the sensor.

Runtime 0.1.27 supplies generic owned wake sets: GPIO sources for Light, active-low
crown on EXT0 plus active-high sensor on EXT1 for Deep, and the existing alarm
timer. No Watch wiring, chip registers, UI or schedule is added to firmware.
All 15 current apps use the shared motion-aware sleep adapter. Exact alarm
reconciliation and quick-control radio suspend/resume remain in place.

## Software and observable device checks

Software gates cover both chip profiles, complete feature writes/readback,
stale/held IRQs, every preparation and rollback transfer fault, retry, registration
ownership, legacy ABI prefixes, source coexistence, native cleanup, alarm boundary
priority, retained apps, current-store admission/execution and target links.
Historical GPIO 0.4.2/PMU 0.5.3 packages are rebuilt from frozen exact source inputs
and must match their original hashes. The current overlay alone replaces them
with GPIO 0.5.0/PMU 0.6.0 and adds IMU 0.3.0.

Hardware checks need no serial connection:
1. In Light sleep, try one tap, then a deliberate pair. Check that the pair wakes
   the prior app and the crown still wakes it. Repeat after ordinary navigation.
2. In manually selected Deep sleep, repeat the same checks. A valid double tap
   should start a fresh Clock; one tap should leave the display dark.
3. Let an alarm become due in each mode. Check its visual/notification behavior,
   including saved Silent/DND and volume settings.
4. Repeat sleep/wake cycles and observe accidental wakes during ordinary handling.
5. Measure current separately if validating battery impact. No power-saving,
   sensitivity, false-positive rate or physical reliability result is claimed.

Sources:
- https://github.com/Xinyuan-LilyGO/TTGO_TWatch_Library/blob/9884d62113cd2f7aa77cd179c346b9017eb08301/schematic/T_WATCH_S3.pdf
- https://github.com/lewisxhe/SensorLib/tree/477fc682e9ed30ced39774f3b7e93a1504968884/src/bosch/bma4xx
- https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32s3/api-reference/system/sleep_modes.html
