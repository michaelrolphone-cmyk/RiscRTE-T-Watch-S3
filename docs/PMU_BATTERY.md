# AXP2101 battery percentage

The PMU driver reads the AXP2101's existing fuel-gauge estimate from register
`0xA4`. It does not estimate percentage from battery voltage, substitute a
demonstration value, or upload a battery model. The clock's existing ABI keeps
`255` plus `RISC_BATTERY_PROFILE_MISSING` as its unavailable representation.
This legacy flag does not distinguish all reasons an estimate is unavailable.

## Read-only admission

A percentage is published only when all six I2C reads succeed and:

- `0x00[3]` reports the battery present.
- `0x68[0]` says battery detection is enabled.
- `0x18[3]` says the fuel gauge is enabled.
- Both reset controls `0x17[3:2]` are clear.
- The BROM writer enable `0xA2[0]` is clear.
- The full byte from `0xA4` is in `0..100`, inclusive.

`0xA2[4]` selects ROM or SRAM; it is not a profile-valid flag. Neither it nor
`0xA4[7]` is treated as a validity bit. A real zero and a real 100 remain valid.
The guards reject disabled, reset, programming, absent and out-of-range states;
they do not prove that a battery-specific calibration was installed or that
the gauge has converged after power-up. The documented register interface has
no separate SOC-ready or model-accuracy flag.

A successful transport with unavailable SOC still returns the measured
millivolts and charge-direction flag. Any failed read returns `false` and leaves
an initialized unknown sample, never a prior percentage or a partial success.
The sampling path performs no register writes. Startup, sleep and teardown
retain the existing power policy, including the 100 mA charging ceiling.

## Manufacturer evidence and accuracy

- X-Powers AXP2101 datasheet V1.4, section 6.11 (page 28), documents the gauge
  output and recommends programming the selected battery's model for better
  accuracy. Registers `0x00`, `0x17`, `0x18`, `0x68`, `0xA2` and `0xA4` are in
  section 6.13.2 (pages 31, 34, 49 and 56). The gauge and battery detection are
  enabled at POR; ROM is the default model selection.
  [Pinned manufacturer datasheet](https://github.com/lewisxhe/XPowersLib/blob/d6997586e68f65afd51baa775903df930db39821/datasheet/AXP2101_Datasheet_V1.4_en.pdf)
- XPowersLib `d6997586e68f65afd51baa775903df930db39821` checks battery presence
  then returns `0xA4` in `getBatteryPercent()`. Its separate `writeGaugeData()`
  resets the gauge and transfers 128 model bytes through `0xA1`; this driver
  deliberately does not call or reproduce that write flow.
  [Read path](https://github.com/lewisxhe/XPowersLib/blob/d6997586e68f65afd51baa775903df930db39821/src/XPowersAXP2101.hpp#L2392-L2399)
  and [model programming](https://github.com/lewisxhe/XPowersLib/blob/d6997586e68f65afd51baa775903df930db39821/src/XPowersAXP2101.hpp#L511-L565).
- The user's T-Watch-S3 reference, TTGO_TWatch_Library
  `9884d62113cd2f7aa77cd179c346b9017eb08301`, enables battery detection and
  voltage ADCs in its PMU initialization. Its PMU ADC example displays
  `getBatteryPercent()` without programming a model in that initialization.
  [Initialization](https://github.com/Xinyuan-LilyGO/TTGO_TWatch_Library/blob/9884d62113cd2f7aa77cd179c346b9017eb08301/src/LilyGoLib.cpp#L475-L518)
  and [example](https://github.com/Xinyuan-LilyGO/TTGO_TWatch_Library/blob/9884d62113cd2f7aa77cd179c346b9017eb08301/examples/peripheral/PMU_ADC/PMU_ADC.ino).
- Newer LilyGoLib `92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43` has separate
  470 mAh and 940 mAh model arrays and a calibration path. Their existence
  does not establish which model is installed in a particular physical watch.
  [Model arrays](https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43/src/LilyGoWatchS3.cpp#L27-L50)
  and [calibration](https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43/src/LilyGoWatchS3.cpp#L577-L598).

The displayed number is therefore the hardware's estimate, with accuracy
dependent on its existing model and learning state. Physical accuracy remains
unverified. Calibrating a replacement cell would require confirmed cell/model
identity and a separate validated configuration/programming contract.

## Regression coverage and hardware follow-up

`CC=gcc python3 scripts/test_contracts.py` exercises both board fixtures. The
PMU cases cover present/absent battery; disabled detection/gauge; both reset
bits; programming with ROM or SRAM selected; valid 0/1/42/99/100; rejected
101/127/128/200/255; failure at each of the six I2C transactions; recovery after
failure; charge direction; no register writes while sampling; and teardown
without charger, CPU or gauge-policy changes.

No test here has accessed a physical watch. If the display remains unknown,
the useful read-only diagnostic is the raw `0x00`, `0x17`, `0x18`, `0x68`,
`0xA2` and `0xA4` values plus transaction success, sampled while the battery is
connected. Those values identify the failed guard without changing charger,
rail, gauge-enable or battery-model settings.
