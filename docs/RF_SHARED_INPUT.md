# RF Waterfall shared text input 0.3.4

This recipe opts only RF Waterfall into `PORTABLE_RF_SHARED_TEXT_INPUT` and
`PORTABLE_TEXT_INPUT_CLIENT`. It starts from the complete published Spectrum
union `e9eeefcbaf35eb67a71fc46c8079ede9bccce863`; Spectrum 0.5.4, LoRa 0.1.14,
Files, all other app/provider payloads and existing grants are preserved.

## Source and feature provenance

Watch RF 0.3.3 is the 241,200-byte ELF with SHA-256
`f05b5ec08db1b1a7f8c7e3133c69b504e8e293d90f76bedcf2d93f0089b1c46b`.
It comes from Utilities `fc0bdbbbc600ce891e60c44d091fce0586ade7d8`,
canvas System `14762601b3fa7bbeeac5ed565a6825534bf74dca`, and Watch profile
`089868395268b696c05651c33816345bfe0425df`. The supplied predecessor
`clients.json` binds its exact compiler flags, full Contexts catalog, source
closure, fonts and alarm suffix ABI. The published profile documentation is
`docs/watch-1.1.10-peer-handoff/source-recipe.json`.

X4's separately packaged RF 0.3.3 is different source and bytes. Its Utilities
pin `c12781b2d4e08772d06078bfff7441276cb5a7a8` adds operation-scoped app-data
storage and retained startup/temporal/fingerprint cleanup corrections. This
new Watch component carries those corrections. Thirteen RF model/format
headers are byte-identical between those two prior pins and must remain so.
The startup scope helper is hash-locked. No SD persistence source is imported.

The new adapter is clean published System
`7fb13b09b4dac275a8111b224784f8a472f39264`. Native Runtime remains
`64c8e52e46fd91e8fdafd636db04eed88f0c51a9`. Utilities is an explicit clean
40-character source commit supplied by the caller. Generic opt-out RF remains
0.3.3; only the selected component manifest becomes 0.3.4.

All predecessor feature flags remain in order. Additions select shared text,
checked storage, custody, terminal retention, existing prelaunch guards,
full-font Watch color/frozen icons and loader-safe LTO. The original full font
bytes and catalog are verified. No font subset or section GC is used. The
canonical relocation normalizer and loader-preserving metadata compactor are
hash/ABI checked; raw and normalized pre-compaction ELFs are retained.

The generated Watch presentation preinclude selects the shared System
PaperPresentation.h private contract and defines the legacy RF presentation
guard. This retains all model source bytes and uses the same existing strong
adapter implementation, while aligning its appended battery suffix across
translation units. It avoids the old private-prefix LTO type mismatch without
suppressing warnings or changing fonts. The selected Watch color profile still
returns no Paper presentation. The generated header and canonical source headers
are included in dependency provenance.

## Reproduction

Set `NATIVE_APP_CC` to pinned Xtensa GCC 8.4.0 esp-2021r2-patch5 and expose
pyelftools 0.32 on `PYTHONPATH`. All output directories must be new. Set `U_SHA`
to the selected clean Utilities commit and `U` to that checkout. Use this
committed product recipe as `W_TOOLS` and the frozen Watch profile as `W`.

```sh
python scripts/build_rf_shared_input.py --device watch \
  --system "$SYSTEM_7FB13B09" --utilities "$U" --utilities-commit "$U_SHA" \
  --runtime "$RUNTIME_64C8E52" --watch-profile "$W" --watch-tools "$W_TOOLS" \
  --baseline "$DECODED_SPECTRUM_STORE" --predecessor-record "$WATCH_CLIENTS_JSON" \
  --output "$RF_BUILD"
python scripts/assemble_watch_rf_shared_input.py \
  --baseline-components "$SPECTRUM_COMPONENTS" --native-candidate "$FILES_CANDIDATE" \
  --rf-build "$RF_BUILD" --runtime "$RUNTIME_64C8E52" \
  --system "$SYSTEM_7FB13B09" --output "$RF_COMPONENTS"
SANITIZE=1 ASAN_OPTIONS=detect_leaks=0 python scripts/assemble_watch_rf_shared_input.py \
  --baseline-components "$SPECTRUM_COMPONENTS" --native-candidate "$FILES_CANDIDATE" \
  --rf-build "$RF_BUILD" --runtime "$RUNTIME_64C8E52" \
  --system "$SYSTEM_7FB13B09" --output "$RF_COMPONENTS" --verify-only
python tests/test_rf_shared_input_recipe.py
```

Assembly verifies the source Spectrum handoff, both admission receipts, complete
bootfs inventory, ancestor native image, all partition bytes outside bootfs/bank
state, authenticated bank digests and complete-cohort admission. It preserves
113 store paths and 55 ELFs and requires at least two free SPIFFS blocks. Only
`waterfall.elf`, `waterfall.json`, `boot.json`, and `cohort.json` change. The sole
authority addition is `ui.text-input@1` instance 0 for RF. All shared hosts remain
byte-identical. The full firmware image is reconstructed only in memory.

Target builds and software admission do not execute target instructions or
qualify radio/capture/navigation/sleep on hardware. No flashing occurs. Delivery
remains held until 2026-10-12 23:30 UTC. Integrate this exact component delta
into any newer authorized union and repeat whole-cohort admission; never replace
newer or paused source work with this independent baseline.

Explicit Home uses PORTABLE_APP_HOME_GUARD to cancel uncommitted editor and
learning/capture state, then exit after verified cleanup. Saved records and
ordinary local Back semantics remain unchanged. Watch Home explicitly selects
springboard.elf; X4 retains its existing resident default.elf destination.
