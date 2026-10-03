# RiscRTE T-Watch-S3 hardware packages

Future-target, software-only driver preparation for the **non-Plus LILYGO
T-Watch-S3**. This is not a RiscRTE firmware port and has not run on a watch.

- [Hardware inventory, sources and coverage](docs/HARDWARE_INVENTORY.md)
- [Exact runtime backfill contracts](docs/CAPABILITY_BACKFILL.md)
- [Shared manifest-to-driver mapping contract](docs/HARDWARE_MAPPING.md)
- [Variant selector](board.json), [physical manifests](hardware), and
  [dependency/instance order](load-order.json)
- [Verification and remaining limitations](docs/VERIFICATION.md)

The board manifest owns wiring, addresses, buses, polarity and power settings.
Chip drivers accept `hardware.device@1`, verify compatible/type/version, and use
that configuration. There are no watch pin constants inside chip drivers. One
package can serve multiple devices through independently mapped ELF instances
and scoped dependency contexts. The mapper/instance loader is future runtime work.

There is **no default physical variant**. Eight explicit alternatives cover the
published SX1262 433/868/915 MHz and SX1280 2.4 GHz versions with BMA423/BMA456H.
Select only after confirming the actual watch, antenna band and sensor. An ASIN,
package installation or radio command response is not that confirmation.

The 17 builds comprise 16 active packages plus the deprecated, manually selected
`i2c.bus.touch` compatibility package. The new graph uses the same `twatch-i2c`
package twice, with separate system/touch bus instances. Runtime raw controller,
GPIO, I2S, carrier, Wi-Fi and HCI providers must be backfilled; missing providers
fail activation. The Wi-Fi driver reuses Garden's shared implementation/contract.

## Software checks

```sh
python3 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
.venv/bin/python scripts/test_contracts.py
.venv/bin/python scripts/build_twatch_drivers.py
.venv/bin/python scripts/check_twatch_drivers.py
```

The build locates `xtensa-esp32s3-elf-gcc` on PATH or the existing PlatformIO
installation; `TWATCH_CC` overrides it. It compiles target layout assertions,
checks ELF32/Xtensa/DYN, exports and imports, then creates one `.rte.zip` per
package and a hashed catalog under ignored `dist/`. No script opens serial ports,
resets, flashes, deploys, signs or releases anything.

Existing watch package versions move from 0.1.0 to 0.2.0; new board/BLE packages
start at 0.1.0. The reused Wi-Fi package is 0.1.2. Protocol API versions are
separate: `radio.lora@2` and `rtc.clock@2` replace their former incomplete tables.
See [third-party provenance](licenses/NOTICE.md) and [SDK pins](sdk/SOURCES.json).
