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

Use generic RiscRTE commit
`e27d3d089086d79f06edeff4c2bd35f6e6243444` for this software checkpoint. The
canonical app SDK remains byte-identical to the earlier commit recorded under
`sdk/app/SOURCES.json`; the SDK pin and firmware pin serve different purposes. A stock older heartbeat firmware lacking app grants or
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

## Optional verified SPIFFS image

CI also uses pinned PlatformIO `tool-mkspiffs@2.230.0` to build a separate bootfs
image for every explicit profile, then unpacks each image and compares all14
files byte-for-byte with its deployment ZIP. The image size is0x4f0000, page256,
block4096. The adjacent JSON records the deployment checksum, image checksum,
tool executable checksum, source revision, partition offset and round-trip result.
These files are in the same CI artifact under `clock-images/`.

To reproduce one locally after verifying its bundle:

```sh
.venv/bin/python scripts/build_clock_store.py \
  dist/clock-deployments/twatch-clock-0.1.0-<profile>.zip \
  --mkspiffs /path/to/tool-mkspiffs/mkspiffs_espressif32_arduino
```

The script never flashes. The output is a **store image only**, not runtime
firmware or a bootloader. Use it only with the matching explicit partition table
and a generic runtime build that supplies the required native backends. Image
checksums are recorded per build; cross-platform filesystem-tool binaries are
not claimed to produce identical physical SPIFFS layouts. Payload round-trip
identity is checked on every build.

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

## First physical boot checklist

Before installing, record the physical unit's model/revision and select exactly
one matching profile. Record the Watch commit, deployment ZIP SHA-256, bootfs
image SHA-256, generic runtime commit/build identity, firmware SHA-256 and the
partition-table SHA-256 together. The SDK pin alone is insufficient: use the
runtime revision whose native-provider and five-module integration checks have
passed. The pinned software checkpoint below supplies that revision and test evidence;
this repository does not yet certify a physical firmware/board combination.

Confirm that the selected build mounts `bootfs` at `/bootfs`, uses the stated
partition dimensions and SPIFFS settings, and supplies the scoped GPIO, I2C,
SPI and monotonic-clock providers. Confirm its configured serial console route
and use 115200 baud where applicable. Installation and power cycling are separate
physical actions; none of these build/verification commands performs them.

For the first supervised boot, retain the complete serial log from the earliest
build-identity line, not only the last error. Record the screen with a photo and
then a short video covering at least three seconds of operation. A successful
clock candidate should show `RTE_BOOT board=validated drivers=admitted`, followed
by `WATCH_CLOCK ready time=rtc` or `WATCH_CLOCK ready time=unset`. Confirm that
seconds advance for a valid RTC, or that uptime advances while `TIME UNSET`
remains visible. Observe for at least one minute for resets, flicker or recurring
errors. This observation is a first-boot check, not endurance qualification.

| Observation | Evidence to retain and next check |
| --- | --- |
| No serial output | Record the selected console route, host port and firmware build identity; this alone does not identify a driver failure. |
| `RTE_BOOT error=storage-mount` | Retain the numeric code and partition/image hashes; check partition and SPIFFS settings. Do not format as an automatic recovery. |
| `RTE_BOOT error=manifest` | Retain the complete `detail` text, `boot.json`, `board.json` and deployment checksum. Check matching SDK/contracts and scoped provider availability. |
| `RTE_BOOT error=runtime` before any clock-ready line | Retain the complete `detail` and preceding log; driver admission does not prove that PMU, panel or RTC startup succeeded. |
| `WATCH_CLOCK error=display-grant-or-api` or `display-format` | Record the runtime commit, grant policy and display table/format diagnostic; check the canonical API and 240x240 RGB565 support. |
| `WATCH_CLOCK error=brightness`, `frame-*`, `present` or `present-timeout` | Retain the exact error, elapsed time, screen state and full log; inspect the display/provider transfer and cleanup result. A ready line must follow completed presentation. |
| `WATCH_CLOCK ready time=unset` with an advancing uptime | This is the intended fallback for an invalid/voltage-low/unreadable calendar. Record it; the app does not set RTC time or infer a timezone. |
| `WATCH_CLOCK ready time=rtc` but a blank, mirrored or incorrectly colored screen | Retain a photo/video and logs, plus the physical revision. A software completion token does not verify wiring, orientation, electrical timing or visible output. |
| `RTE_BOOT state=idle reason=app-returned` | Retain any preceding `WATCH_CLOCK error` and cleanup diagnostics; a continuously running clock is not expected to return normally during this observation. |

The deployment deliberately requires all five drivers. A physically missing RTC
or a failed RTC **driver startup** can prevent the whole graph from starting;
the app's `TIME UNSET` fallback only applies after the app runs (for example, a
voltage-low calendar or a failed subsequent read). Do not interpret that fallback
as permission to omit a required driver or silently bypass startup failure.


## Pinned integrated software checkpoint

- Runtime source: [`e27d3d089086d79f06edeff4c2bd35f6e6243444`](https://github.com/michaelrolphone-cmyk/RiscRTE/commit/e27d3d089086d79f06edeff4c2bd35f6e6243444).
- Runtime [integration CI run37099823064](https://github.com/michaelrolphone-cmyk/RiscRTE/actions/runs/37099823064)
  passed both host integration and the actual ESP32-S3 firmware/ELF/candidate build.
  This revision includes the IDF4 partial-initialization cleanup fix and focused
  failure-retention checks; use this pin instead of the earlier checkpoint.
- The runtime test pins Watch source `aa7b03c15a59aa99b2d60ae20905edbdf62e35e6`.
  It loads the actual app and five modules using host instruction-set ELFs,
  through the real Runtime, dependency graph and generic CPU port. Only low-level
  GPIO/I2C/SPI operations are modeled. All 115200 reconstructed SPI pixel bytes
  match each production-renderer golden frame (valid RTC and TIME UNSET).
  No RTC date writes occur; bad PMU identity and SPI failure roll back with zero
  remaining model resources. See the runtime's pinned
  [CPU port report](https://github.com/michaelrolphone-cmyk/RiscRTE/blob/e27d3d089086d79f06edeff4c2bd35f6e6243444/docs/CPU_PORT.md).
- The integration profile `sx1262-915-bma423` is a test fixture, not an inference
  about the physical unit. Target Xtensa artifacts are built separately; the
  host integration does not execute Xtensa instructions or verify physical DMA.

The subsequent Watch checklist/pin changes are documentation-only. App, driver,
manifest and selected store contents are unchanged from the integration-tested
Watch source. Each newly built deployment ZIP nevertheless has its own source
revision and checksum because it includes `INSTALL.md` and provenance. Keep the
checksum from the artifact actually selected; do not relabel an older ZIP or
assume its hash remains valid. The app SDK pin remains `be6efce33...`, independently
of the runtime firmware revision above.

For a source build, use a new isolated runtime checkout at the pinned full SHA,
install its `requirements-ci.txt` into a dedicated environment, and set a
checkout-local `PLATFORMIO_CORE_DIR`. Copy only the verified, explicitly selected
Watch bundle's `store/` contents into that checkout's empty `build/store/`.
Run `pio run -e esp32s3 -j 1`, then `pio run -e esp32s3 -t buildfs -j 1`.
Retain `.pio/build/esp32s3/{firmware.bin,bootloader.bin,partitions.bin,spiffs.bin}`
together with the full source SHA and SHA-256 of each image. These commands build
software only. Do not run `build_apps.py`: it installs the runtime test heartbeat
and replaces the selected Watch application/store.

The generic runtime CI candidate contains its own heartbeat test store. Its
complete bundle is **not** a preassembled Watch clock deployment. For tomorrow's
supervised installation, use the explicit Watch clock store with the pinned
runtime and matching partition layout, and verify the recorded image hashes.
Physical profile selection, installation and hardware observations
remain outstanding. No successful hardware execution is claimed here.
