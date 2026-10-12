# Audio Spectrum Watch modal-policy recipe

This is a local-only, independent successor to the exact public Timecard Watch
recipe `e491c63b51f20447aafbdd938c560ec5bae59ae1`. It selects the complete qualified
Timecard union, including the previously selected Spectrum 0.5.4. RF recipe files
and commits are not inputs to this branch.

The component recipe replays the exact selected Spectrum 0.5.4 compiler command
with source-root relocation and the sole feature addition
`-DPORTABLE_TEXT_INPUT_POLICY`. It retains all functionality flags, original full
fonts, the complete Contexts catalog, models, storage formats, and existing
manifest authority. The successor manifest version is 0.5.5. The selected System
source is `fd4b1e52fe2a49c3c4c22f9ccd4c98a91f88afa0`; the exact Utilities pin must be
finalized in `selection.json` before target compilation.

## Local verification

- Run `python -m unittest discover -s tests -p test_spectrum_policy_recipe.py -v`.
- `scripts/build_spectrum_policy.py` compiles, normalizes, validates, and compacts
  only Spectrum, using the pinned GCC 8.4.0 esp-2021r2-patch5 compiler.
- `scripts/test_spectrum_policy_flagoff.py` rebuilds the original and repaired
  source profiles without the policy flag and requires both to match the exact
  selected Spectrum 0.5.4 ELF.
- `scripts/inspect_spectrum_target_stack.py` measures actual Xtensa entry-frame
  operands and checks static modal storage. This is not a dynamic peak-stack or
  physical-execution claim.
- `scripts/assemble_watch_spectrum_policy.py` overlays Spectrum onto the exact
  qualified Timecard store, repacks all 113 files, and runs the production Runtime
  admission path for all 55 ELFs. Repeat with `SANITIZE=1 --verify-only` and compare
  the complete normal and sanitized receipts.

The baseline has two free SPIFFS blocks. Assembly keeps at least two; if needed,
it compacts only seven explicitly allowlisted ordinary unsigned manifests with
duplicate-key rejection, decoded-value equality, and
before/after receipts. `boot.json` remains byte-identical. All other ELF bytes,
fonts, native firmware, shared-text host, scene host, and existing permissions
are preserved. Reserve failure remains a hard failure.

Only the overlay, boot store, bank state, and evidence are written. A prospective
full-image hash is streamed from the exact existing native ancestor and the two
replacement components. No full image is created, no hardware is exercised, and
no remote publication is performed by these scripts.

The selected compiler has a previously reproduced intermittent internal linker
double-free abort. The recipe retries only that exact signature with unchanged
command, source, flags, and output path. Every nonzero-exit output is quarantined
and rejected; only a successful link can enter validation or compaction. Attempt
counts and log/output hashes are included in the build and flag-off receipts.

## Qualified checkpoint

The compiled public recipe is `0499a3a3cd3e0461e61c6c93a444090657d41e9e`;
receipt-only documentation commits do not change that build identity. See
[`qualified/qualification.json`](qualified/qualification.json) for the bound
source/target/cohort evidence. Source CI and recipe CI passed. The target is
234,932 bytes; disabled-policy output exactly matches selected Spectrum 0.5.4.
Normal and ASan/UBSan cohort receipts match across all 55 ELFs. All 58 old/new
JSON files reject duplicate keys; seven unsigned manifest whitespace-only
changes save 2,994 bytes and retain the two-block floor. No physical-device
execution, full-image delivery or flashing is claimed.
