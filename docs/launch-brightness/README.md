# T-Watch 1.1.39 launch brightness

Cumulative successor to the exact 1.1.38 native Home release. The immutable
producer handoff binds all 18 target app ELFs, their import/export inventories,
predecessor hashes, predecessor versions, and the complete 37-file replacement
set. Each app manifest changes only its version; the cohort changes only its
product version and product source revision.

All remaining 84 store files are byte-identical to 1.1.38, including Home 0.16.0,
Springboard, driver payloads, manifests, and boot policies. Native firmware and
ELF are taken from the original official 1.1.37 native evidence archive and
independently compared with the exact 1.1.38 factory. Native origin and baseline
product source are separate pins.

## Qualification

`build_launch_brightness_release.py` verifies immutable source pins and runs:

- 126 first-completed-frame brightness host cases, normal and ASan/UBSan
- 192 app data-custody host cases, normal and ASan/UBSan
- Preserved Springboard controller tests, including eight real-controller cases
  with three clean invocations each
- Strict replay of all 18 target ELFs with pinned compiler, specs, symbols and
  bounded recognized linker-retry evidence
- Scope/authority mutation rejection tests
- All 59 installed ELFs admitted by the unchanged production native firmware,
  normal and ASan/UBSan, with no hardware or storage I/O
- 272 both-bank preserving-update, interruption, torn-write and rejection cases
- Independent verification of the complete factory, store, evidence archive,
  preserving kit, checksum inventory and protected byte ranges

The optional `--qualified-replay` and `--qualified-host` inputs permit local
reuse only after all source, payload and evidence checks pass. CI omits both
options and performs fresh pinned qualification and replay. There is no expected
hash override or alternate recipe path in the product entrypoint.

Finalization requires the immutable 1.1.38 product source, complete store digests,
and factory digest. Publication remains disabled until that baseline is official
and every product gate passes. The release tag is `test-launch-brightness-1.1.39`.

No build or qualification script accesses a physical watch. Factory images erase
saved data. A preserving update requires a fresh complete readback through a
separately authorized device flow. Software qualification is not hardware proof.
