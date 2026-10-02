
# RiscRTE-T-Watch-S3

Loadable RiscRTE drivers for the LILYGO T-Watch-S3 sold as Amazon ASIN `B0GPQ3TGLM` (ESP32-S3, 1.54 inch 240x240 ST7789, FT6336U, AXP2101, BMA423, PCF8563, DRV2605, MAX98357A, SX1262 or SX1280, 470 mAh).

This is the T-Watch-S3, not the T-Watch-S3 Plus. The Plus adds GNSS and a different cell. These drivers do not claim a GPS UART.

Nothing in this tree has been run on a watch. Status on every manifest is `derived-unverified-on-device`. Pin and rail choices come from LilyGoLib `docs/hardware/lilygo-t-watch-s3.md` and the `lilygo_twatch_s3` Arduino variant.

## Load order

`platform-clock-v1` is the existing RiscRTE clock ELF. Do not load `i2c-esp32s3-v2` here; that driver talks to firmware Wire on the T5S3 pins.

1. `platform-clock-v1`
2. `twatch-gpio` provides `gpio.bank`
3. `twatch-i2c` provides `i2c.bus` on GPIO10/GPIO11
4. `twatch-i2c-touch` provides `i2c.bus.touch` on GPIO39/GPIO40
5. `twatch-pmu` enables ALDO2, ALDO3, ALDO4, and BLDO2 at 3.3 V, locks charge current at the 100 mA code, and provides `board.battery`
6. `twatch-panel` provides `display.output` (ST7789 RGB565) and owns the backlight pad
7. `twatch-touch` provides `input.touch.raw`
8. `twatch-imu` provides `motion.accel`
9. `twatch-rtc` provides `rtc.clock`
10. `twatch-haptic` provides `haptic.effect`
11. `twatch-button` provides `input.navigation` from BOOT/GPIO0 only
12. `twatch-lora` provides `radio.lora` probe and register read
13. `twatch-speaker` provides `audio.output` on the MAX98357A pads
14. `twatch-mic` provides `audio.input` on the SPM1423 pads
15. `twatch-ir` provides `ir.transmit` on the IR12-21C

## Charge current

The 470 mAh cell is damaged by a high charge setting. LilyGO says keep it below 130 mA. The Amazon listing notes say not to raise the library default above 125 mA. `twatch-pmu` writes AXP2101 register `0x62` with code `4` (XPowersLib 100 mA) and fails start if the readback is anything else. There is no API to raise it.

`board.battery` returns millivolts from the AXP2101 ADC. `percent` is 255. This ELF does not invent a state of charge.

## Audio

`twatch-speaker` owns GPIO48 BCLK, GPIO15 WCLK, and GPIO46 DIN. `open` accepts 8000, 16000, 22050, or 44100 Hz, mono or stereo s16le. Mono is copied to both slots. `set_gain` is software scale. `silence` clocks out zeros and then holds the pads low. There is no MAX98357A SD pin on this map, so hardware gain is not claimed.

`twatch-mic` owns GPIO44 clock and GPIO47 data. `open` accepts 8000 or 16000 Hz. `read` returns s16le frames from a 64:1 PDM decimator. `level` is the mean absolute value of the last read, not a calibrated SPL.

ESP32-S3 PDM conversion exists only on I2S0, and the I2S FIFO has no CPU port. These ELFs bit-bang the pads instead of taking a GDMA channel. The requested rate is the PCM contract. The bit clock is the GPIO loop, not a PLL, so pitch and capture rate will drift. Neither ELF has been heard or captured on a watch.

## Infrared

The onboard part is an Everlight IR12-21C transmitter on GPIO2, the same pin LilyGO's IRsend example uses. The published pin map has no receiver, so there is no decode capability. `send_nec` writes an 8-bit address and command with their complements. `send_nec32` writes a 32-bit LSB-first frame. `send_raw` takes mark/space/mark microseconds at 20-56 kHz. Idle is pin low. The carrier is a busy loop, not the RMT peripheral, and has not been received by a target.

## What is not a driver yet

- LoRa packet TX/RX. `twatch-lora` resets the radio, waits on BUSY, and can read an SX126x status or register. SX1280 boards share the pads; a failed SX126x probe is a failure, not a guessed radio.
- POWER key as navigation. It is the AXP2101 PWRON pin (2 s on / 6 s off) and the PMU already owns address `0x34`.
- RTC interrupt GPIO17, IMU interrupt GPIO14, LoRa IRQ GPIO9. Left unclaimed.

## Build

```text
python3 scripts/check_twatch_drivers.py
python3 scripts/build_twatch_drivers.py
```

The build needs `xtensa-esp32s3-elf-gcc`. Each ELF exports only `t5_driver_get` and uses RiscRTE provider ABI v2.
