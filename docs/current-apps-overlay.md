# Current applications release overlay

`apps/current-apps-sources.json` is the explicit final cohort. Its four source
commits are integrated default-branch ancestors. The old update/audio/Points
source files remain historical custody inputs and are not rewritten.

Build the final artifact with clean checkouts at those exact source pins:

```
TWATCH_CC=/path/to/xtensa-esp32s3-elf-gcc python3 scripts/build_current_apps.py \
  --system-apps /sources/system-apps --utilities /sources/utilities \
  --productivity /sources/productivity --runtime /sources/runtime \
  --baseline /artifacts/audio-tools-common.zip --output /output/current-apps
```

The output directory must be empty. The baseline must pass the existing exact
historical audio verification. All 15 application ELFs, the alarm service, and
two update providers are rebuilt and structurally validated. Current catalog
icons must equal the current System registry. Current paired Clocks share the
same Points headers and CUE client as the service and every portable app.

Pass `--current-apps-artifact-dir /output/current-apps` to
`scripts/build_latest_main_flash.py` along with its existing arguments. It
applies the current payload only after historical custody checks. Exactly 37
store files may change: 36 application/provider payloads plus boot.json. The
other 21 files remain byte-identical. The only policy additions are Alarms'
namespace1 preferences and alarm-service's read-only namespace1 alarm_volume
binding. The catalog remains 13 entries; the store remains 58 files.

After assembly, test the actual final BIN, not a reconstructed policy:

```
SANITIZE=0 TWATCH_CC=/path/to/xtensa-esp32s3-elf-gcc \
python3 scripts/test_current_apps_runtime.py \
  --runtime /sources/runtime --system-apps /sources/system-apps \
  --utilities /sources/utilities --productivity /sources/productivity \
  --current-apps-artifact-dir /output/current-apps \
  --bin /output/final.bin --output /output/current-runtime
```

Repeat with `SANITIZE=1 ADDRESS_SANITIZE=1 ASAN_OPTIONS=detect_leaks=0` and a
separate output directory. The verifier accepts `--image` instead of `--bin`
for local isolated SPIFFS replay. Both modes decode actual bytes read-only,
verify every current payload and boot policy, perform real Runtime admission,
and run six real Runtime/default-Clock scenarios using host-architecture
substitutions. JSON manifests and boot policy are never substituted. Current
service host compilation includes ALARM_VOLUME_CONTROL. Empty startup permits
only the existing validated namespace4 Points expiration ledger write; no
configuration writes, radio/audio I/O, bank I/O, or unexpected RTC writes pass.
These are software checks, not physical hardware qualification.

Upload the exact output as `twatch-current-apps-<Watch SHA>` in the same run
attempt as the final main BIN. The inner `current-apps.zip` contains only
`current-apps-build.json`, `source-profile.json`, `files/**`, and `licenses/**`.
The final manifest's `current_apps_overlay` records its exact archive and build
record hashes, the full record, and changed/preserved file partitions. The
Clock source map uses Watch-relative paths and SHA256 digests. Historical
`points_overlay` evidence continues to describe the historical input bytes.
