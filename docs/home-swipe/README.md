# Home swipe correction: Watch 1.1.20 / Home 0.11.6

This recipe starts from the exact qualified Watch 1.1.19 image, SHA256
`fe9fd6bc304de29023c1ac3d485a65af880c38d41ab4da7f963d0985e7da997d`.
It replaces only `default.elf`, changes only Home's manifest version, and seals
the cohort at Watch 1.1.20 with the committed recipe revision.

## Preservation boundary

- Exactly 113 store files and 55 ELFs remain.
- All 54 other ELFs and all other 110 store paths are byte-identical.
- Native ELF and firmware, boot configuration/grants, font inputs, and Home
  compiler feature flags are retained.
- Only four of the original Home target's 98 dependencies may change:
  `apps/clock/crown.c`, `apps/clock/launcher_touch.h`, `apps/clock/nova/nova.h`,
  and `apps/runtime_features/clock_runtime.h`.
- The 1.1.19 Home manifest is already compact. Its exact formatting is preserved;
  only `"version":"0.11.5"` becomes `"version":"0.11.6"`.
- The ordered SPIFFS build must retain at least two free 4096-byte blocks. There
  is no fallback which strips fonts, apps, providers, features, or other metadata.
- All 16 MiB full-image bytes outside bootfs and paired bank state are unchanged.
- Normal and sanitized production Runtime admission must agree on the exact
  selected native composition and all 55 ELFs.

This recipe does not publish, deliver, or flash. A full initial image flashed at
`0x0` erases settings and app data. Host admission does not execute Xtensa target
instructions and is not physical-device verification.

The combined Home target also includes the displayed-clock
correction described in [the clock correction notes](../clock-drift/README.md).
Although its source header is shared, this assembly replaces only Home's ELF;
the other 54 ELFs and native firmware remain byte-identical to Watch 1.1.19.

## Behavioral qualification

The Home gesture model covers leftward launcher swipes and top-edge downward
quick-panel swipes at modeled raster times from 0 through 335 ms,
including 8–10 ms touch-sampling gaps. The repaired source passes all 40 gesture
traces in normal and ASan/UBSan modes; the predecessor passes 14 of 40, with 26
lost or misrouted traces. Fifteen boundary scenarios cover taps/long presses,
invalid samples and gaps, multitouch/contact changes, queue overflow canceling
an earlier queued swipe, quick-panel close/reopen, and top-edge horizontal replay.
Capture-boundary checks retain picker and quick-panel state without allocation
or app launch. These times describe the model and do not measure physical watch
touch latency, hardware responsiveness, or end-to-end on-device frame timing.

The retained regression batch also passes launcher/return/touch transfer,
quick-action/radio configurations and contexts in normal and sanitized modes,
33 stable face IDs with cyclic picker behavior, 96 byte-identical golden frames,
20,000 signed/unsigned division cases, and 162 guarded Points production frames
(18 scenarios across nine faces). The existing fast-wake test runner applies the
required `WATCH_CONTEXTS_CLIENT` define to `nova.c` in both modes.

The branch CI workflow runs the new gesture suite, the existing fast-wake suite,
six Home-overlay guard tests, and the retained full-image/custody boundary tests.
Target reproduction and the exact-image cohort qualification below additionally
require the retained artifact inputs; CI source tests alone do not establish
that a final full image has been qualified.

## Target reproduction and build

The baseline Home 0.11.5 ELF is 862880 bytes with SHA256
`90388f2269badefae66d8ba7fc844fd7d7af481392e55bb79f9e898e4ff81875`.
The target recipe replays its exact retained build command, the original C++
boot-effect compilation, relocation normalizer, and loader-metadata-v3 compactor.
Toolchain programs and libgcc are hash-pinned in `toolchain-pins.json`.

Use Python with pyelftools installed; the retained local build-tools installation
is detected by the target builder. For assembly, the established local environment
uses `PYTHONPATH=/tmp/x4-keyboard-091-python`.

```sh
ROOT=/workspace/shared/watch-home-swipe-20261012
BASE=/workspace/shared/watch-evening-1119-20261012
CC=/workspace/scratch/c744abbbbd60/watch-build-tools/platformio-core/packages/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-gcc
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/tmp/x4-keyboard-091-python

COMMON=(--baseline-product "$BASE/product"
  --baseline-clock /workspace/shared/watch-sleep-failure-clock-build-0115
  --system /workspace/shared/watch-fast-wake-20261012/system-clock
  --utilities /workspace/shared/watch-fast-wake-20261012/utilities-clock
  --compiler "$CC")

# Use fresh output paths. Baseline sources and receipt must match all 98 hashes.
python "$ROOT/product/scripts/build_home_swipe.py" "${COMMON[@]}" \
  --product "$BASE/product" --version 0.11.5 \
  --output "$ROOT/build-evidence/repository-reproduction"

# Commit and test the patch before the successor target build.
python "$ROOT/product/scripts/build_home_swipe.py" "${COMMON[@]}" \
  --product "$ROOT/product" --version 0.11.6 \
  --allow-change watch:apps/clock/crown.c \
  --allow-change watch:apps/clock/launcher_touch.h \
  --allow-change watch:apps/clock/nova/nova.h \
  --allow-change watch:apps/runtime_features/clock_runtime.h \
  --output "$ROOT/home-build"
```

## Cumulative image and qualification

Run the gesture regression suite and the existing applicable Watch tests first.
The focused assembly tests are independent and exercise exact-delta and authority
rejection guards:

```sh
python "$ROOT/product/scripts/test_home_swipe_assembly.py"
python "$ROOT/product/scripts/test_clock_raster_gestures.py" \
  --system-apps /workspace/shared/watch-fast-wake-20261012/system-clock \
  --utilities /workspace/shared/watch-fast-wake-20261012/utilities-clock

ARGS=(--baseline "$BASE/final"
  --baseline-clock /workspace/shared/watch-sleep-failure-clock-build-0115
  --native-candidate /workspace/shared/watch-files-shared-input-candidate-20261012
  --home-build "$ROOT/home-build"
  --runtime /workspace/shared/watch-runtime-file-source-20261012
  --output "$ROOT/final"
  --materialize)

python "$ROOT/product/scripts/assemble_home_swipe_watch.py" "${ARGS[@]}"
SANITIZE=1 ASAN_OPTIONS=detect_leaks=0 \
  python "$ROOT/product/scripts/assemble_home_swipe_watch.py" "${ARGS[@]}" --verify-only
cmp "$ROOT/final/receipts/final-normal.json" "$ROOT/final/receipts/final-sanitized.json"
sha256sum "$ROOT/final/WATCH-1.1.20-FULL-INITIAL-ERASES-DATA.bin"
```

The output records exact input and output SHA256 values, source commit/tree,
feature flags and dependency hashes, the three changed store paths, all preserved
paths, reserve floor, immutable native composition, and full-cohort admission.
No claim of final qualification is made until those commands pass on the
committed source and actual target.
