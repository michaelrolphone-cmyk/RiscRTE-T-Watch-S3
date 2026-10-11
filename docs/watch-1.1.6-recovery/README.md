# Watch 1.1.6 recovery diagnostic composition

This successor preserves the delivered 1.1.5 complete Watch store: 25 applications, 30 providers, all 111 file paths and every existing capability policy. It adds the qualified host-owned crown exit/five-second recovery path and the offline radio-entropy correction for direct Files sharing. Software qualification does not establish physical button timing, reliable emergency restart, Wi-Fi/BLE pairing, heap margins or a data-preserving upgrade.

The complete initial image erases internal data. General settings and Wi-Fi persistence across a full flash remain unfinished. This Watch profile has no SD provider or SD-resident apps and does not opt in to shared SD settings.

## Source composition

See `source-recipe.json` for exact source IDs and status. The baseline image is the delivered Watch 1.1.5 diagnostic; its SHA-256 and per-file store receipt are mandatory inputs to the builder. Source publication and final exact-source admission must complete before a successor binary is delivered.

Nineteen generic applications use the delivered compact Watch canvas adapter lineage plus the native crown hook (`System Apps 6ea07eb`). Replacing that adapter with the newer shared X4-era adapter would exceed the unchanged boot partition. The compact adapter retains Watch NOVA drawing, local navigation/sleep, Quick Controls, BLE broadcast, motion wake, low-battery behavior, alarm/cue lifecycle, and Contexts capture/workflows/face catalogue. It does not claim newer X4 shared-keyboard, resident-shell or paper UI behavior.

Scanner retains its published local Watch keyboard source (`Utilities 377d471`) because the newer shared text-input provider is absent from this Watch cohort. Other generic Utilities applications use the reconstructed Contexts recovery branch. Current Productivity applications use their normal color path with an explicit absent optional paper interface, without adding a provider or grant.

Files and the scene host use the common modern System integration. The existing default clock, returnable Clock, Lists, 3D Viewer and the other 29 providers retain their delivered ELF and manifest bytes. Every reused file stays bound to the baseline receipt; existing source/build receipts remain part of the evidence package. Preserved/non-cooperating code, already-running legacy alarm modals or uncertain cleanup rely on the native deadline fallback.

## Build and verification

`build_watch_crown_recovery.py` requires clean named checkouts, the verified decoded baseline, original full image, and original composition receipt. It refuses changed baseline bytes, missing apps/providers, authority changes, file additions/removals, version regressions, or an unqualified shared-settings opt-in. It compiles 21 applications and the scene provider using the pinned ESP32-S3 GCC 8.4 toolchain, checks imports/exports and structural ELF validity, and applies loader-preserving metadata compaction with original symbol sidecars.

The 23-entry catalogue remains available for launch and Contexts workflows. Existing app requirements and grants remain byte-equivalent; only rebuilt versions change. Files is 1.5.28. Product version 1.1.6 is separate from the historical board-baseline 1.1.6 tag.

Use the qualified common System `assemble_shared_files_bundle.py` with `--target watch`, this product's `docs/shared-files/product.json`, exact native firmware/ELF, and unchanged verified bootloader/partition/app-data inputs. Complete-store Runtime admission must use the selected native profile's capacities rather than the historical default host limits. Validate the resulting full image's partitions, erased inactive bank, bank state/CRC, SPIFFS round trip, policy graph and every ELF against the exact compiled public resolver.

The initial local preflight fitted 111 files into the original 5.1 MiB boot store with 45 free blocks. This is an image-layout result, not measured free heap or hardware reliability. Final immutable receipts supersede any local preflight measurements.
