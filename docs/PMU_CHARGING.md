# AXP2101 charging and observable power states

PMU0.6.1 makes charger initialization explicit while keeping the existing
100mA constant-current setting. It extends read-only `board.battery@1` samples
for Battery1.1.0 power screens; no native Runtime change is required.

## Initialization and cleanup

Startup reads `0x62` (constant-current limit), `0x18` (charger/gauge/watchdog
control) and `0x50` (TS mode). It preserves the upper `0x62` bits, sets code4
(100mA) and reads it back before enabling charging. If `0x18[1]` is already set,
startup does not rewrite that register. This avoids needless charger cycling
and safety-timer resets on every app/driver activation. If disabled, it changes
only bit1, verifies the complete control byte and confirms TS mode is unchanged.
A read or mismatch is a failed initialization, not a verified charge state.

An attempted enable remains pending until startup succeeds. A failed or
ambiguous enable write is rolled back to the original enable bit. Cleanup
preserves unrelated bits, verifies the restoration and retains its I2C claim
when transport prevents confirmation. A later quiesce retries; another startup
cannot take over that claim. The 100mA setting is never restored to an inherited
higher current. Once startup commits, normal unload and all sleep paths leave
charging enabled. Sampling and sleep do not toggle the charger.

Precharge/termination currents, termination enable, charge-target voltage,
input limits, TS mode/current source, JEITA thresholds, die-temperature
protection, safety timers, detection/gauge settings and battery model are
unchanged. Thus 100mA is the configured constant-current limit, not a claim
about measured current or every possible charger phase.

## Temperature evidence and limits

The pinned manufacturer's non-Plus S3 schematic shows TS pin31 tied to ground
through fixed R182100R, rather than a cell thermistor. The reference board
initialization configures TS as a fixed input, explicitly describing the lack
of battery-temperature detection. This driver deliberately does not reproduce
that disabling/configuration write: inherited TS mode is observed and preserved.
It cannot verify which board revision or battery is physically fitted.

Consequently this increment must not claim cell temperature, a 43C cell
threshold, "too hot" from a fabricated temperature, or guaranteed charging on
every inherited configuration. If TS is still configured to inhibit charging,
that remains a separately observable/configuration issue requiring confirmed
hardware policy. No protection is bypassed to make a charging indication appear.

## Status contract

The existing four-byte sample retains legacy voltage, SOC and charging behavior.
The companion `PortablePowerStatus.h` defines bit2 as an extended-status-valid
marker. It is set only after all existing six read transactions succeed and
battery detection is enabled. Bits3..7 describe usable VBUS (`0x00[5]`), charger
enabled (`0x18[1]`), charger-done state (`0x01[2:0]==4`, also requiring battery
and usable input), battery presence (`0x00[3]`) and PMIC thermal regulation
(`0x00[1]`). Clients must check the marker. A failed read clears all results.
Old clients ignore new bits; old providers yield basic telemetry without invented
USB, presence, completion or thermal state.

Charger complete is separate from estimated100%. Thermal regulation means the
PMIC is limiting charge; it is neither a cell-temperature measurement nor proof
that charging is completely stopped. VBUS-good is usable input, not detection
of a cable, charger type or charging wattage. Current direction is an observation,
not a current measurement.

The AXP2101 performs the charge cycle autonomously when usable input, charger
enable and protection conditions allow. ESP deep sleep does not itself require
the charger to stop. Existing sleep code changes only interrupt masks/status;
charge-start/USB IRQ wake remains masked. A sleeping display or static SOC does
not establish that charge current stopped.

## Primary sources inspected

- [AXP2101 datasheet V1.4](https://github.com/lewisxhe/XPowersLib/blob/d6997586e68f65afd51baa775903df930db39821/datasheet/AXP2101_Datasheet_V1.4_en.pdf),
  section6.7: autonomous charging/conditions, safety timers and temperature
  protection; register00/01 (page31),18 (page34),50 (page45),61-65 (pages47-48)
- [LILYGO non-Plus S3 schematic](https://github.com/Xinyuan-LilyGO/TTGO_TWatch_Library/blob/9884d62113cd2f7aa77cd179c346b9017eb08301/schematic/T_WATCH_S3.pdf),
  sheet1: TS/R182 fixed resistor and main battery wiring
- [LILYGO reference initialization](https://github.com/Xinyuan-LilyGO/TTGO_TWatch_Library/blob/9884d62113cd2f7aa77cd179c346b9017eb08301/src/LilyGoLib.cpp#L444-L479),
  TS policy and charger settings; these are evidence, not copied charge policy

## Software and remaining qualification

Run `python scripts/test_pmu_charge_status.py` for all initialization I2C-failure
boundaries before/after device mutation, enable/current readback mismatch,
retained rollback/retry, repeated activation, 32 preserved TS modes and8192
status combinations. `test_contracts.py`, `test_pmu_cold_boot_sleep.py`,
`test_deep_sleep.py` and `test_hybrid_sleep.py` protect existing driver/sleep behavior.
Target builds validate all17 ELF packages and hashes, including immutable legacy
GPIO0.4.2/PMU0.5.3 custody. The released1.0.2 source/product record uses PMU0.6.0;
that record is untouched. The next integration cohort selects PMU0.6.1.

Physical current flow while awake/light/deep asleep, actual termination,
protection response and the owner's reported sleep-charging symptom have not
been tested. Software checks do not close that hardware qualification.
