# Watch clock software candidate

This is a watch application and selected external ELF drivers for the generic
RiscRTE runtime. It is not a successful hardware-test report. No script in this
repository flashes, resets, erases or accesses a serial device.

## Build the application and deployment

Use the repository's pinned ESP32-S3 GCC8.4.0 esp2021r2-patch5 toolchain (the PR
workflow downloads and verifies it). `TWATCH_CC` can select that compiler.

```sh
python3 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
python3 scripts/build_twatch_drivers.py
python3 scripts/build_clock_app.py
python3 scripts/build_clock_deployment.py --profile all
```

`all` produces eight separate explicitly named bundles, not a guessed board
variant. For a known unit, replace `all` with its matching profile stem from
`hardware/`. Verify the physical board/model/revision before installing; these
profiles exclude T-Watch-S3 Plus and CC1101 retrofits. The clock uses only common
hardware, but that does not authorize guessing an unknown full-board variant.

Each `dist/clock-deployments/twatch-clock-0.1.0-<profile>.zip` contains:

- `store/default.elf` and `store/default.json`: real application and identity.
- `store/boot.json`: default path, five selected external driver manifests, and
  explicit application grants for display instance5 and RTC instance8.
- `store/board.json`: a clock-only projection of the named profile, preserving
  original instance IDs and canonical controller namespaces/mappings.
- `store/{gpio,i2c,pmu,panel,rtc}/{driver.elf,manifest.json}`: independent modules.
- `packages/`: the original versioned `.rte.zip` packages for those five drivers.
- Original profile, board baseline descriptor, install notes and
  `deployment-record.json`: SHA-256/size for every payload, watch source SHA,
  runtime SDK source pin, and explicit projection/rail transformations.

Check the outer ZIP checksum in `dist/clock-deployments/catalog.json`, then verify
all inner files against `deployment-record.json` before installation. Do not
merge a deployment into a stale store. The versioned ZIP is authoritative; the
adjacent extracted tree is only a build convenience.

## Runtime and store installation contract

Use generic RiscRTE source compatible with the exact SDK commit recorded under
`sdk/app/SOURCES.json`. A stock older heartbeat firmware lacking app grants or
native GPIO/I2C/SPI providers cannot run this clock. The loader must mount the
selected `store/` at `/bootfs` and provide bounded, scoped native GPIO, I2C, SPI,
and monotonic-time providers. Watch chip protocols and pin assignments remain in
the external drivers and board JSON.

The current generic runtime's example partition table is an **8MiB layout**:
factory app offset0x10000 size0x300000; bootfs SPIFFS offset0x310000 size0x4f0000.
The watch inventory documents16MiB physical flash; the example uses only the
first8MiB. Do not assume an already installed watch has this partition table.
Confirm the exact runtime build and partition table before any separately
performed hardware deployment. No unattended flashing or formatting is provided.

For an isolated runtime checkout, stage this bundle's `store/` as `build/store/`
and run the generic runtime's single-job firmware and `buildfs` build. Do not run
its heartbeat `build_apps.py` afterward: that replaces `default.elf` and boot
configuration. Use matching firmware, bootloader, partition table and SPIFFS
artifacts from that one build; never combine images from unrelated revisions.
Store mounting must remain non-formatting on failure.

## Expected behavior and morning checks

The app draws a240x240 RGB565 digital clock, RTC date, and uptime. It reads the
PCF8563 through `rtc.clock@2`; it never writes time, alarms, or calibration.
A voltage-low flag, invalid calendar, missing RTC grant, or failed read displays
`TIME UNSET` and `--:--` rather than inventing time from uptime/build time. A valid
RTC value is displayed as stored, with no assumed timezone or daylight-saving
conversion. There is no time-setting UI or network time synchronization.

The five drivers are GPIO, system I2C, AXP2101 PMU, ST7789V3 panel, and PCF8563 RTC.
PMU setup retains the100mA ceiling and enables only ALDO2/ALDO3 for display and
backlight. Touch, secondary I2C, LoRa, BLE/Wi-Fi, audio, haptics, IR and motion are
not loaded. Existing battery/PMU dependency edges keep display power alive.

On the real unit verify: correct profile and pins; valid module-store mount;
independent ELF admission; visible display and expected orientation/colors;
backlight behavior; sane RTC date/time or honest unset state; seconds advancing;
and stable operation without watchdog resets or repeated error logs. Preserve
serial diagnostics from boot and any `WATCH_CLOCK` error/status lines. A host
fixture verifies software behavior only; it does not establish electrical timing,
actual ELF execution on the MCU, DMA/resource ownership or PMU safety on a device.


## Simulation evidence and limits

`python3 scripts/test_clock.py` executes the production app and renderer against
bounded host service models under UBSan: grant/table rejection, RTC validity,
frame cleanup, failed submit, presentation failure/timeout and normal updates.
These are app unit tests, not a full runtime or CPU-emulation result. Existing
`test_contracts.py` executes production peripheral drivers against transport
models separately. `clock_frame_fixtures.py` generates valid/unset RGB565 and PNG
frames using the production renderer; `dist/clock-frames/expected.json` records
inputs and expected raw-frame hashes for runtime integration tests.

Espressif supplies an ESP32-S3 QEMU fork, but its documented feature matrix does
not implement the general-purpose SPI, I2C, GPIO matrix or ESP32-S3 LEDC needed
by this exact watch chain. Its virtual framebuffer is a different virtual
device. No QEMU/Wokwi executable was installed in the task environment. Therefore
this candidate does not claim a full-chip watch simulation; host peripheral
models and target compilation are the relevant current evidence. Sources:
[Espressif QEMU guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/tools/qemu.html)
and [official feature matrix](https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/README.md).

Future sleep/wake can stop a clock invocation at the generic lifecycle boundary:
this app holds no worker tasks, timers or persistent caller buffers, releases
unsubmitted frames and capability grants on return, and reads RTC anew on a
fresh invocation. No deep-sleep or wake implementation is included, and no
shutdown request or wake behavior is assumed from the current runtime API.
