# Watch 1.1.19 cumulative test build

The exact source and component selection is in `selection.json`. This recipe
seals an already-qualified, complete Watch union by updating only the product
version and source revision in `cohort.json`. Native firmware, applications,
providers, fonts, features, grants and boot metadata remain byte-identical.
The Watch has no SD card. RF Spectrogram remains the published 0.3.4.

Run `scripts/assemble_evening_watch.py` with the selected baseline directory,
its exact handoff, the retained native candidate, Runtime checkout and a fresh
output directory. Repeat with `SANITIZE=1 ASAN_OPTIONS=detect_leaks=0` and
`--verify-only`; the normal and sanitized receipts must match. Add
`--materialize` to produce the single 16 MiB full initial BIN for offset 0x0.

The full initial BIN erases settings and application data. This recipe never
uploads, delivers or flashes it. Host admission and target structural custody
do not execute Xtensa instructions or establish physical-device behavior.
