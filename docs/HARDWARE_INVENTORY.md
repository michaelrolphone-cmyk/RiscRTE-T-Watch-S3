# Hardware inventory and coverage

## Evidence and variant boundary

The primary wiring/rail source is LILYGO's
[non-Plus hardware page at 92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43](https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43/docs/hardware/lilygo-t-watch-s3.md).
The corresponding [board initialization](https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43/src/LilyGoWatchS3.cpp)
and [radio model selection](https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43/src/radio/LilyGoRadioHelper.h)
were inspected. The manufacturer [wiki](https://wiki.lilygo.cc/products/t-watch-series/t-watch-s3/)
also lists the two LoRa families and touch reset limitation.

**Physical PCB revision is unconfirmed.** The linked
[schematic file named T_WATCH-S3 25-03-24.pdf](https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43/schematic/T_WATCH-S3%2025-03-24.pdf)
contains older `T_WATCH-2020&GPS_V08`, `V1.4`, 2021 sheet titles and a GPS sheet.
Its filename is not proof of the installed PCB revision or a GPS receiver in the
non-Plus watch. Configurations follow the explicitly named non-Plus software
hardware map. `revision` in the catalog names a **configuration variant**, not a
claim to have inspected a physical revision. Silicon revisions are `unspecified`.

The original repo names ASIN B0GPQ3TGLM but supplies no per-unit BOM. The current
manufacturer page says BMA423 is being replaced by BMA456/BMA456H; an observed
chip ID must match the selected profile (0x13 or 0x16). SX1262 and SX1280 are
explicit alternative compatible IDs, never inferred by trying the wrong driver.
The same manufacturer tree has CC1101 retrofit examples, but its non-Plus
hardware table names SX1262/SX1280; no CC1101/GPS/Plus support is claimed here.

## Devices and physical resources

All GPIO numbers below are taken from the pinned manufacturer table. JSON copies
these values; the reusable C code obtains them through the injected typed config.

| Physical device | Bus/address and pins | Rail/resource | Implemented ELF behavior |
|---|---|---|---|
| ESP32-S3 GPIO | authorized pads, no direct MMIO | global GPIO/PWM/bus owner | `twatch-gpio`: token adapter to shared GPIO owner; rejects unsupported flags/stale handles |
| System I2C | controller0, SDA10/SCL11,100kHz | 0x19/0x34/0x51/0x5a, distinct address owners | `twatch-i2c`: monotonic address leases, serialized repeated-START transactions, bounded raw controller |
| Touch I2C | controller1, SDA39/SCL40,100kHz | 0x38 only | second **instance of the same** `twatch-i2c` package |
| AXP2101 | system0x34, IRQ21 active low | ALDO2 backlight, ALDO3 display/touch, ALDO4 LoRa, BLDO2 haptic enable | ID check, configured 3.3V rails,100mA charge limit/readback, battery ADC/charging status, PWRON short/long IRQ consume; restores rail/IRQ configuration during cleanup |
| ST7789V3 | display SPI: SCLK18/MOSI13/no MISO; CS12/DC38/BL45; reset absent | SPI2 selected by board-port mapping; ALDO2/3;115200-byte frame | canonical RGB565 frame leases, asynchronous row transfers, endian conversion, present status/cancel, real PWM brightness |
| FT6336U | touch0x38, IRQ16 active low; reset absent | ALDO3 | coherent two-contact reports, hardware contact IDs, DOWN/MOVE/UP, independent queues, GAP/snapshot; never puts touch into unrecoverable sleep |
| BMA423 or BMA456H | system0x19, IRQ14 reserved | +3V3 | selected ID validation, reset,100Hz ±4g acceleration enable, signed raw XYZ; IRQ pad owned, sample acquisition polled |
| PCF8563 | system0x51, IRQ17 active low | RTC supply and VBACKUP | valid Gregorian dates2000–2099, BCD/VL/century rejection, running clock, minute-resolution alarm and ACK, unused clock-out disabled |
| DRV2605 | system0x5a, no GPIO IRQ | BLDO2 enable | device ID admission, ERM library1 effects1–123, sequence terminator, GO/stop, retryable safe stop |
| MAX98357A | I2S1 TX: BCLK48/WS15/DATA46 | clocked I2S/DMA; no separate SD pin in map | mono/stereo s16 PCM,8/16/22.05/44.1kHz, gain exactly once, bounded writes, zero frames/safe drain |
| SPM1423HM4H-B | I2S0 PDM RX: CLK44/DATA47 | exclusive PDM-capable I2S0/DMA |8/16kHz mono signed PCM capture, partial results, mean absolute level (not calibrated SPL) |
| IR12-21C | GPIO2 active-high transistor drive | hardware carrier timing owner | NEC8/complement and NEC32 encoding, raw mark/space validation,20–56kHz33% carrier,150ms maximum envelope, idle low |
| BOOT key | GPIO0 active low/pullup | boot strap remains reserved during boot | debounced canonical navigation BACK, neutral rearm, foreground suppression |
| POWER/PWRON key | PMIC pin, not an ESP32 GPIO | hardware2s on/6s off unchanged | PMU-owned latched short/long IRQ; no duplicate I2C owner |
| SX1262 **or** SX1280 | radio SPI SCLK3/MOSI1/MISO4/CS5; RESET8 low/BUSY7 high/DIO1 IRQ9 high | ALDO4, distinct SPI controller; explicit antenna band and TCXO config | modem configuration, packet TX/RX, CRC/timeout/status, payload/RSSI/SNR, cancel/reset-safe teardown; caller-driven bounded polling |
| Wi-Fi integrated radio | unit0, station/AP | shared CPU RF stack/heap, coexistence arbitration | reused Garden `wifi`: validated credentials, join state, AP and IP addresses; raw radio provider missing |
| BLE integrated controller | unit0 HCI | RF coexistence and controller buffers | `twatch-ble`: command/ACL packet validation and bounded command/event/ACL transport; raw controller provider missing |

The8 profile alternatives encode SX1262 band430–440/863–870/902–928MHz or
SX1280 2400–2500MHz, each with one of the two sensor IDs. These are hardware
matching ranges, **not legal transmit authorizations**; future grants must apply
local channel/power policy. SX1262 TCXO code0 follows RadioLib's1.6V default used
by the manufacturer's default `radio.begin()` path. Actual fitted oscillator,
antenna band, screen orientation and motor calibration remain physical checks.

## Other on-chip, power and connector resources

| Resource | Ownership / disposition |
|---|---|
| ESP32-S3 dual LX7,240MHz | CPU/ABI port; these ELFs are Xtensa, not RISC-V binaries |
|16MiB QSPI flash /8MiB OPI PSRAM | boot/module-store/linker/cache/allocator port; reserve flash/PSRAM pads26–37. No guessed partition map or filesystem driver |
| Micro-USB D-/D+ | ESP32-S3 GPIO19/20 reserved to one USB PHY/role owner; manufacturer says connector charges/programs and cannot power external devices. No VBUS source driver or automatic host activation |
| USB device/CDC, host/class protocols | reuse canonical Reader USB providers only after board-role/power and low-level imports are ported; not built/claimed active here |
| DC1 | ESP32 supply: never altered by PMU driver |
| VBACKUP / RTC coin-cell path | preserve existing configuration; no guessed recharge policy |
| unused DC2–5/ALDO1/BLDO1/DLDO1/CPUSLDO | not enabled by this manifest; not free external GPIO |
| reset, boot straps, battery switch | hardware/boot semantics remain intact |
| SD, GPS, IR receiver | not declared on the pinned non-Plus map; no fabricated drivers |

Filesystem/module storage, networking protocols, BLE host/GATT, USB role startup,
sleep/wake and RF coexistence are recorded in the backfill inventory. They are
not evidence of a completed watch runtime port.
