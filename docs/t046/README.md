# T046 shared keyboard integration

Compose over the SHA-pinned delivered X4 .115 / T-Watch 1.1.29 / Waveshare .32.
System source checkpoint: c88523a (scene 0.4.8; text-input 0.1.8).
Shared scene/text components change on all three products. Native, Home,
ordered input, clock/RTC/sleep/Files and existing SD contents are preserved.
Watch and Wave additionally restore the qualified Points in Time shared caller
(version 0.6.19) with modal policy and explicit Save behavior. Its Wave profile
retains native-height rendering and matches contacts to that transform.
Wave repairs missing ui.text-input dependencies/grants for Points and BLE Scanner.
All other application executables remain byte-identical to the exact baseline.

The exact-baseline recipe validates old store reproduction, repeated output,
complete file differences, native hash, paired bank state, and SD bindings.
Full BIN is an initial-install test image at 0x0 and erases internal user data.
X4 also supplies a cumulative changed-SD overlay to merge onto existing contents.
No device was flashed; hardware and vehicle validation remain pending.

Component builders: System scripts/build_text_input_services.py with profiles
watch-compact, color-dynamic, and full. The color packages use the existing
Watch scripts/compact_current_elf.py metadata-only compaction, retaining the
original ELF and verifying all loader sections, symbols and relocation targets.
No source fonts are regenerated. Native SDK for the shared modules: a91edf3.

Build using the committed build_t046_components.py (X4: minimal/t046/build_components.py), then assemble_t046.py (X4: minimal/t046/assemble.py). Pass explicit --system, --runtime, --watch-tools, --target and --output roots. All final artifact source hashes are recorded in docs/t046/evidence.

Color Points rebuild: scripts/build_t046_points.py, using Productivity T046,
System c88523a for Watch, System 5f353a0 (ed74c682 plus the Points presentation gate) for the Wave native-height
adapter (pass --wave), Utilities 710eddc and Runtime a91edf3. The shared providers
are always the final System T046 components. Receipts hash the compiled closure.
