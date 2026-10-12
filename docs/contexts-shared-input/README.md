# Contexts 0.4.3 shared text input

Build only the deployed scene client from the published Utilities commit `2a06ff127e6f7c7d687b1361bed05da97aa05b2d`, with System fixed at `7fb13b09b4dac275a8111b224784f8a472f39264`. The generic source manifest remains unchanged. The selected product manifest advances from 0.4.2 to 0.4.3 and adds only `ui.text-input@1`; existing grants remain unchanged.

`baseline.json` traces the actual deployed client bytes to Utilities `fc0bdbbbc600ce891e60c44d091fce0586ade7d8`; the entry/controller/scene-view bytes were still identical at the authorized Utilities baseline `4beb9778d300ec9f6b18448e1ec86317e063c98c`. `catalog.c` is the exact predecessor catalog, not a reduced replacement. The scene client embeds no font payload: the existing scene host, text host, and all other provider bytes remain frozen.

The Watch inherits its Contexts face-name header, full catalog, compiler flags, exports and metadata compaction. The X4 inherits alarm API 2, settings mask 0x274, native toolbar and RF-only source selection. The only new feature flag is `PORTABLE_CONTEXTS_SHARED_TEXT_INPUT`. The X4 old immutable selected image and old flat 0.4.1 fallback remain intact; a new immutable 0.4.3 pair is added and selected.

The complete Watch cohort contains 55 ELFs and 113 store files. X4 retains 43 internal and 48 selected SD ELFs, 106 store files, all 90 existing SD files and adds two new immutable files. Composition requires at least two free SPIFFS blocks and independently decodes the new store, checks every unchanged file, retains native bytes, and streams the full image hash without writing a full-initial image.

Run the device recipe with clean exact-source checkouts and a fresh output directory. Run Watch assembly twice (normal and `SANITIZE=1 --verify-only`) or X4 `qualify_evening_102.py` on the composed output. This validates host-side structural admission only; it does not execute Xtensa instructions or qualify hardware. Full initial flashing erases internal saved data. No flashing, binary publication, or delivery is performed here; artifacts remain held until 2026-10-12 23:30 UTC. Paused SD-settings changes are excluded.

## Reproduction

Set `SYSTEM`, `UTILITIES`, `RUNTIME`, `WATCH_PROFILE`, `WATCH_TOOLS`, and `BASELINE` to clean checkouts and the exact Timecard handoff components. Utilities is pinned above; Runtime is device-specific in the builder; Watch profile is `089868395268b696c05651c33816345bfe0425df`. Use the original Espressif GCC 8.4.0 / 2021r2-patch5 compiler through `NATIVE_APP_CC`.

```sh
python scripts/build_contexts_shared_input.py \
  --system "$SYSTEM" --utilities "$UTILITIES" \
  --utilities-commit 2a06ff127e6f7c7d687b1361bed05da97aa05b2d \
  --runtime "$RUNTIME" --watch-profile "$WATCH_PROFILE" \
  --watch-tools "$WATCH_TOOLS" --baseline "$BASELINE" --output "$TARGET"
python scripts/inspect_contexts_target_stack.py --build "$TARGET" --output target-stack.json
```

The flag-off target test uses `--baseline-utilities` at 4beb9778, the same five source/profile paths, and `--output` for a small JSON receipt. It compares full raw ELFs and every allocated section and removes temporary builds. Shared-input default-off preservation is distinct from validating the selected opt-in product.

```sh
python scripts/assemble_watch_contexts_shared_input.py \
  --baseline-components "$TIMECARD_COMPONENTS" --native-candidate "$NATIVE_CANDIDATE" \
  --contexts-build "$TARGET" --runtime "$RUNTIME" --system "$SYSTEM" --output "$CANDIDATE"
SANITIZE=1 ASAN_OPTIONS=detect_leaks=0 python scripts/assemble_watch_contexts_shared_input.py \
  --baseline-components "$TIMECARD_COMPONENTS" --native-candidate "$NATIVE_CANDIDATE" \
  --contexts-build "$TARGET" --runtime "$RUNTIME" --system "$SYSTEM" --output "$CANDIDATE" --verify-only
```

## Final public-source qualification

All target and complete-cohort checks passed using the exact public source and recipe commits in [qualification.json](qualification.json). [Target build](target-build.json) records the compiler command and dependency closure; [normal](normal-admission.json) and [ASan/UBSan](sanitized-admission.json) receipts cover the complete installed cohort. [Custody](candidate-custody.json), [packing](packing.json), [target stack](target-stack.json), and [flag-off identity](flagoff-target.json) preserve the boundaries and measured limits.

[Source CI](utilities-ci.json) passed the 508 normal/sanitized scenarios, 86 unit tests and unchanged pipeline regressions. [Detailed source results](results.json) retain 38 paired render/storage hashes for each of four profile/flavor combinations. [Visual review](visual-review.json), [supplemental regressions](supplemental-regressions.json), [CI-only font pin correction](ci-font-pin-correction.json) and the [independent final review](independent-review.json) are recorded without changing any production font payload. [Compiled recipe CI](compiled-recipe-ci.json) is green.

This receipt commit changes documentation and JSON evidence only. Reproduction must use the compiled recipe SHA in qualification.json, which is also embedded in the target and cohort records. Artifacts remain held until 2026-10-12 23:30 UTC; no binary is published by this receipt commit.
