# Watch 1.1.12 clock-first wake test

This focused successor to delivered 1.1.11 includes its deep-sleep crown fixes,
bounded native metadata-read scheduling, and the source-qualified Clock 0.11.3
fast-wake opt-in. It is a hardware test image, not hardware-qualified firmware.

Clock presents the selected face and correct saved time policy before admitting
optional radio, broadcast and Contexts services on separate foreground turns.
Successful light wake returns directly to Clock without the old timed splash.
Alarm reconciliation, low-battery policy, capability grants, provider ownership
and paired-boot confirmation remain enforced. The service calls themselves are
synchronous; input and presentation run between phases.

Runtime 0.2.23 removes a forced scheduler tick after every 512-byte metadata read.
Reads remain bounded to 512 bytes, with a scheduler checkpoint after 32 KiB or
two milliseconds of read work, plus a final remainder checkpoint. Existing size,
deadline, parser, graph and lifecycle admission remain in place. No new wake-time
checksum or file revalidation is added. The exact native qualification is linked
in `source-recipe.json`.

The original 1.1.11 default Clock is reproduced byte-for-byte before building the
fast opt-in. Its 98-input dependency closure changes only `apps/clock/crown.c`.
The default manifest changes only version 0.11.2 to 0.11.3. Every other app,
provider, manifest, grant and boot policy is byte-preserved, including Files
1.5.30 and the existing Clock return wrapper. Final image admission uses the
selected production Runtime and all 54 app/provider ELFs, both normally and with
ASan/UBSan.

The source and host tests establish removed delay budgets and ordering, not
physical wake latency. Clock `WATCH_WAKE` records provide entry, first frame,
first input poll and service-phase timestamps. Device crown-to-visible-clock
timing, repeated deep/light wake, alarm delivery, BLE and low-battery operation
still need physical qualification.

## Reproduce

Use clean source checkouts and the exact native and Clock materials named in
`source-recipe.json`. Build Clock with
`scripts/build_watch_fast_wake_clock.py` and its pinned System/Utilities inputs;
its unchanged original must match the delivered default before proceeding.

```sh
python3 scripts/assemble_watch_fast_wake.py \
  --runtime /path/to/exact-runtime --system /path/to/exact-system-assembly \
  --native /path/to/qualified-native --clock /path/to/qualified-clock \
  --baseline-image /path/to/WATCH-1.1.11-FULL-INITIAL-ERASES-DATA.bin \
  --output /new/output
SANITIZE=1 ASAN_OPTIONS=detect_leaks=0 \
  python3 scripts/assemble_watch_fast_wake.py \
  --runtime /path/to/exact-runtime --system /path/to/exact-system-assembly \
  --native /path/to/qualified-native --clock /path/to/qualified-clock \
  --baseline-image /path/to/WATCH-1.1.11-FULL-INITIAL-ERASES-DATA.bin \
  --output /new/output --verify-only
```

The full initial image is 16 MiB, starts at flash offset zero, and erases internal
data and settings. No flashing is performed by these build scripts. Preserve the
matching native and Clock symbols for any reset investigation.
