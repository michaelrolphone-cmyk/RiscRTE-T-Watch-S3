# Actual production-store Clock regression

`scripts/test_production_store_runtime.py` consumes delivered profile ZIPs,
SPIFFS images, or already extracted stores. It copies every store byte and keeps
the original input immutable. Only selected executable files in a separate host
copy are replaced with native builds of their actual production sources. Boot,
board, every app policy, and every driver manifest retain identical JSON bytes.
The original complete-store digest and JSON hashes are recorded in
`provenance.json` when `--output DIRECTORY` is supplied.

The test compiles and runs real `Runtime`, `CpuPort`, provider graph, all selected
Watch drivers, the real Points-enabled alarm service, and the current default
Clock with exactly the Launcher/Alarms/Points feature flags used by the delivered
build. Every other app manifest remains in the policy, including return Clock
and Points grants for namespaces 1 and 5. No app, provider, policy or display
substitute is used. Host `dlopen` provides independent driver data/BSS mappings.

Example (paths to sibling repositories and artifacts are supplied explicitly):

```sh
python3 scripts/test_production_store_runtime.py \
  --runtime ../runtime --system-apps ../system-apps --utilities ../utilities \
  --archive /artifacts/wifi-deployments/*.zip /artifacts/points-deployments/*.zip \
  --image /artifacts/wifi-common-bootfs.bin /artifacts/points-common-bootfs.bin \
  --mkspiffs /path/to/pinned/mkspiffs_espressif32_arduino \
  --output /tmp/production-clock-evidence
```

`--store DIRECTORY`, `--archive` and `--image` can be repeated. SPIFFS extraction
uses the same hash-pinned tool and extraction helper as the admission gate.
Add `--expect-prepare-error 'app requirement not uniquely authorized'` to prove
the old Runtime rejects the untouched policy before mapping any module or
performing hardware I/O. UBSan is enabled by default (`SANITIZE=0` disables it);
`ADDRESS_SANITIZE=1` adds ASan. Compiles and test processes have bounded timeouts.

The native fixture models only raw GPIO, two I2C controllers and their register
transfers, and the panel's SPI bytes. I2S and radio entry points are present for
binding the production board but assert if startup attempts audio, join or scan.
The backend presents an empty settings/Points/alarm store. RTC starts at a fixed
valid fixture date. All behavior above these lowest boundaries is production.

Assertions require:

- Admission of the complete production graph, with both Clock/Points namespaces.
- Exactly two actual Clock namespace-1 reads (`watch_face`, `time_format`) and
  one namespace-5 read (`points_cfg`) before its first yield. The alarm service
  has already started, so its later polled reads cannot satisfy this assertion.
- The `WATCH_CLOCK ready` diagnostic, complete nonzero RGB565 Clock output,
  full panel rows before nonzero brightness, and actual touch polling.
- Ordinary default-app return after the test health source stops at `ready`.
  The real Runtime unloads the app and all providers, and CpuPort reports every
  pin/controller quiescent.
- No RTC writes, persistent writes, radio join or scan, and no modified JSON or
  original store bytes before/after execution.

This is a host integration regression. It does not execute the delivered Xtensa
machine code, boot the ESP32 firmware, exercise RF, use credentials, qualify
physical hardware, or navigate the other applications. Their actual unchanged
policies are admitted, but only the current default Clock is executed. Target
ELF integrity, image custody, and physical qualification remain separate checks.
