# Watch 1.1.13 minimal deep-wake startup test

This successor targets the remaining deep-wake delay reported with Watch 1.1.12.
The successful light-wake flow is preserved. Physical latency of this successor
is not yet measured.

On classified deep wake with valid retained native time, the first Clock frame
and crown/touch poll need six provider instances instead of ten. RTC, alarm
service, haptic and speaker wait until afterward. Alarm reconciliation runs
immediately after the first input poll, before sleep/navigation or optional
radio/Contexts startup. Unset native time and cold/reset entry retain RTC seeding.
Due alarms, expiry, output cleanup, stale input cancellation and retained-failure
handling remain enforced. All capabilities become available through the same
existing demand activation and promotion paths.

The native ELF loader obtains regular-file size with fstat instead of seeking to
EOF and rewinding. The exact delivered SPIFFS reproduction removes 1,324 flash
read calls / 338,944 bytes from the Clock size query. This is an I/O operation
count, not a claimed reduction in physical milliseconds. Unsupported fstat keeps
the original seek fallback; limits, deadlines, file admission and cache failure
handling remain unchanged.

Existing bounded native stage/performance observers are enabled in the explicit
crown-wake profile. Clock records the previously unmeasured pre-frame operations
and marks first frame at completed transfer/unblank, before reading sleep settings.
No diagnostic storage scan, file checksum, provider activation or persisted write
is added. Plain stage lines are best-effort over USB and may be lost without a
reader; the fixed-size performance recorder retains aggregate phase durations.
After startup, the existing exact `perf` line command returns its snapshot.
Nested durations must not be summed as independent time. Setup excludes earlier
ROM/bootloader work, and software presentation is not proof of visible pixels.

Files 1.5.30 and all other applications/providers, manifests, capability grants,
boot policy and the Clock return wrapper are unchanged. Only native Runtime,
default Clock ELF/manifest and cohort identity change. The original non-fast Clock
is reproduced byte-for-byte before building the selected Clock 0.11.4. Its pinned
98-input closure changes only crown.c and the fast-only alarm input-cancel signal.

The exact source, native/Clock artifacts and predecessor image are pinned in
source-recipe.json. assemble_watch_deep_start.py enforces complete image admission
against the selected Runtime and every app/provider ELF, normal and ASan/UBSan.
Host and target qualification cannot substitute for a physical wake test.

The broader SPIFFS name-lookup index prototype is excluded. File placement is
unchanged; a separate future experiment will measure layout effects without
changing file contents or admission.

## Reproduction

Use the clean pinned sources and artifact directories from source-recipe.json:

    python3 scripts/assemble_watch_deep_start.py \
      --runtime /exact/runtime --system /exact/system-assembly \
      --native /qualified/native --clock /qualified/clock \
      --baseline-image /delivered/WATCH-1.1.12-FULL-INITIAL-ERASES-DATA.bin \
      --output /new/output

Repeat with SANITIZE=1 ASAN_OPTIONS=detect_leaks=0 and --verify-only for sanitizer
admission. Build/assembly checks run offline, not on each device wake.

The 16 MiB full initial BIN starts at offset zero and erases internal data and
settings. These scripts never access or flash a device. Retain matching native
and Clock symbols for any reset investigation.
