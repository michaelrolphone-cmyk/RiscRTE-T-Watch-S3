# Software verification and limits

Local tools: Clang with UndefinedBehaviorSanitizer, Python3.11/jsonschema4.23.0,
and xtensa-esp32s3-elf GCC8.4.0 esp-2021r2-patch5. Tests execute production driver
C with bounded mock transports. No serial/USB hardware is accessed.

- **34 executable host fixtures:**16 hardware entries on two configurations
  (alternate pins and SX1262/BMA423 versus SX1280/BMA456H), board catalog selection,
  and two simultaneously linked copies of the same I2C driver with independent
  BSS/dependencies. Both instances can own the same address on different buses;
  shutting one down leaves the other usable.
- All fixtures reject incompatible chip/config version/size and duplicate
  hardware dependencies before claims. Applicable fixtures inject partial GPIO/
  controller admission, failed I2C register operations and failed teardown; all
  resources eventually drain after retry. Live address, frame and touch leases
  block release.
- Protocol checks include full115200-byte display transfer and native-to-wire
  RGB565 order, touch contact IDs/UP events, RTC invalid date/BCD/alarm, charge
  ceiling/status, haptic terminator, LoRa packet completion/receive/timeout,
  once-only mono gain, PCM capture, exact NEC marks/spaces, Wi-Fi join state and
  HCI frame bounds. They do not model every electrical/chip erratum.
- **17 target ELFs/packages:** canonical/extension layout assertions, ELF32 little
  endian Xtensa DYN, sole exported `t5_driver_get`, undefined-import allowlist,
  version/identity/dependency metadata, provider sidecar and archive/catalog hashes.
- **8 explicit board alternatives +8 negative mapping cases:** schema, exact
  compatible matching, unique pin/address ownership, scoped bus bindings,
  no unknown fields, charge policy, dependency cycle rejection.
- `git diff --check` checks whitespace. SDK provenance hashes guard exact copied
  canonical/shared contracts.

Commands: see README. The PR workflow runs these checks on Ubuntu22.04 and keeps
unsigned software packages as CI artifacts. Compiler checksum comes from
[Espressif IDF v4.4.8 tools.json](https://github.com/espressif/esp-idf/blob/v4.4.8/tools/tools.json).
A local pass is distinct from remote CI; the PR checks are the source of truth
for its exact submitted head.

Recovered during development: sandbox DNS required authorized network execution;
one initial reference repository name was wrong and corrected to T5S3-Reader;
a GCC8 Xtensa shared-link assertion was eliminated by exact32-bit radio-frequency
arithmetic instead of a64-bit libgcc division helper; stale schema assumptions
about physically absent reset pins were corrected in the watch extension. None
is being reported as an outstanding blocker.

## Pending integration and physical verification

No Reader runtime mapper, independent-instance loader, raw watch controller
backends, firmware image or full watch application is provided. No module was
loaded into an actual runtime. BLE HCI is a controller transport, not a BLE host
stack; Wi-Fi depends on the future CPU stack service. Flash/PSRAM/module store,
USB role/PHY/power adaptation, filesystem/network services and sleep/wake are
port/backlog items. Sensor feature firmware/FIFO/step counters, haptic motor
calibration, LoRaWAN/FSK/ranging and GPS are not advertised implementations.

Actual radio/antenna/sensor/PCB variant, oscillator voltage, electrical timing,
IRQ/wake behavior, motor calibration, battery/charger behavior, display orientation,
audio quality and RF operation remain **unverified on hardware**. Explicit profile
selection and correct runtime providers are required before authorized physical
qualification. No release, merge, default launcher or hardware test occurred.
