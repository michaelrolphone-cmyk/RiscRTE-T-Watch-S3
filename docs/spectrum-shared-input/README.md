# Watch Audio Spectrum shared input

Audio Spectrum 0.5.4 selects the existing `ui.text-input` service for its bounded
name editors. It preserves the deployed analysis, capture, events, signatures,
trends, speech, neural, Contexts and library workflows. Only Audio Spectrum is
selected; other applications keep their existing input paths.

## Source and feature custody

`build_watch_keyboard_spectrum.py` requires the complete qualified LoRa union
(store digest `6b82cf31e572210a26153659c38b6f22ce985cf6248bae6f337a7071e046de8c`)
and its unchanged Audio Spectrum 0.5.3 predecessor, 234,144 bytes, SHA-256
`dc9c242b385f0a38e6c80d4688935b8975404d635aa8ecf7d5b3bf227e502635`.
The exact predecessor `clients.json` receipt binds the frozen full Contexts
catalog, every inherited Watch source and every inherited feature selector.
Unchanged Utilities model inputs and original font bytes are checked by hash.

The isolated component uses published System
`7fb13b09b4dac275a8111b224784f8a472f39264`, unchanged native Runtime
`64c8e52e46fd91e8fdafd636db04eed88f0c51a9`, and an explicit clean Utilities pin.
There is no dependency on paused, unpublished SD source changes.

The new app selection is `PORTABLE_SPECTRUM_SHARED_TEXT_INPUT` together with
`PORTABLE_TEXT_INPUT_CLIENT`. It retains all inherited capture, Contexts,
NOVA, alarm, navigation, sleep, quick-control, and async-frame selectors.
Checked storage, native custody, alarm retention and app-launch guards match
the qualified shared-input clients. The already-published Watch color-only
and frozen-icon selectors preserve the deployed presentation selection.
All six original NOVA font faces remain; no glyph subset is selected.

The pinned GCC 8.4.0/binutils 2.35 linker cannot garbage-collect Spectrum's
software-float dynamic sections. The recipe retains the predecessor's
non-GC section profile, enables LTO without section GC, and roots the original
`SingleFloatDivisionCompat.c` helper. The canonical hash-pinned normalizer
removes only trailing all-zero `R_XTENSA_NONE` padding, as in the predecessor.
The raw linker ELF and normalized pre-compaction ELF are retained in `debug/`;
receipt hashes describe both steps. Production ELF validation runs before and
after loader-preserving metadata compaction.

The component budget is 238,000 bytes, with complete-store packing independently
required to retain at least two free SPIFFS blocks. No app removal, partition
resize, font substitution, or reserve reduction is allowed by the recipe.

## Complete cohort qualification

`assemble_watch_spectrum_shared_input.py` reads the original LoRa component
handoff, verifies matching normal/sanitized receipts, decodes its exact bootfs,
and reconstructs its ancestor image in memory to verify custody. It preserves
all 113 store paths and 55 ELFs, the native firmware, all text/scene provider
bytes, and every existing app/grant. It changes precisely:

- `audio_spectrum.elf`
- `audio_spectrum.json`: version 0.5.4 and additive `ui.text-input@1`
- `boot.json`: additive `ui.text-input@1` grant for Audio Spectrum only
- `cohort.json`: current compiled recipe identity

Run the component builder against a new output directory. Then run the cohort
assembler normally and again with `SANITIZE=1 ASAN_OPTIONS=detect_leaks=0` and
`--verify-only` against that same output. Normal/sanitized receipts must match.
LeakSanitizer is disabled only for executor ptrace; ASan and UBSan remain on.

The assembler emits a four-file overlay and verified bootfs/bank artifacts.
It never writes a full initial firmware image. Native target instructions are
not executed by host admission; hardware capture, PMU and sleep remain
unverified. There is no flashing or delivery. Delivery remains held until
2026-10-12 23:30 UTC. Integrate exact components into any newer authorized union,
preserve unrelated work and grants, and repeat complete-cohort admission.
