# Timecard shared text input integration

Selected Timecard versions: Watch 0.2.13, X4 0.2.16. The recipe changes only
Timecard ELF/manifest, its `ui.text-input@1` instance 0 grant, and cohort metadata.
All other apps, fonts, shared hosts, native firmware, and partitions are held
byte-identical. Original feature profiles are independently pinned per device.

This branch is an integration recipe, not a firmware release. The selected clean application source is
[Productivity 395c48de](https://github.com/michaelrolphone-cmyk/RiscRTE-Productivity/commit/395c48de8fa10b672816c89c02dd9a5d4987a094).
Final published-source qualification receipts are recorded alongside this document. Outputs
are held until 2026-10-12 23:30 UTC. No flashing or hardware validation occurs.
No unpublished SD-settings work is consumed or exported.

The full-initial image digest is streamed without allocating or writing a full
image. Any later full-initial flash erases internal saved data. Preserve a
minimum of two free SPIFFS blocks; no features or fonts may be removed to fit.

Read `baseline-profile.json` for the exact selected predecessor evidence. The
X4 compiler command is explicitly reconstructed from the recovered .55 profile
and the .62 raster-snapshot opt-in; the actual .62 compiler receipt is absent.
The .62 ELF itself is byte-identical to the selected current Timecard ELF.

The already-touched Watch `boot.json` uses compact JSON serialization. Its parsed
value is asserted to be exactly the prior value plus Timecard's single text-input
grant. This formatting-only change provides flash reserve without changing
features, fonts, shared libraries, or any other store file.

The final public-source all-feature candidate has six free SPIFFS blocks, four above the
required two-block floor. Its Timecard ELF is 146,272 bytes. Normal and ASan/UBSan
admission each cover all 55 selected ELFs; 109 of 113 store paths remain byte-identical.
The only changed paths are `timecard.elf`, `timecard.json`, `boot.json`, and
`cohort.json`. The final target bytes also reproduce the independently reviewed preliminary target bytes.

System Apps remains pinned to `7fb13b09b4dac275a8111b224784f8a472f39264`.
The Watch display-specialization and compiler-layout experiments are not selected.
`inspect_timecard_target_stack.py` records actual Xtensa entry-frame operands and
static modal-state ownership. It does not claim dynamic call-chain stack peaks.

## Final qualification

The compiled recipe is [9f366977](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/commit/9f3669771c75e6d472afd8c8af9861600dcc9e5a).
This follow-up changes documentation and receipts only. Always use that compiled
recipe SHA when reproducing the recorded component and candidate digests.

See [qualification.json](qualification.json) for results and receipt hashes,
[target-build.json](target-build.json) for exact compiler flags, imports, sources
and dependencies, [candidate-custody.json](candidate-custody.json) for candidate
hashes and preservation evidence, and [target-stack.json](target-stack.json) for
actual entry-frame measurements. Full [normal](normal-admission.json) and
[sanitized](sanitized-admission.json) admission receipts are included.

The [independent review](independent-public-review.json) passed on these exact
public source and recipe commits. [Source CI](productivity-ci.json) passed all
174 workflow/regression runs and six paired render/storage comparisons using
platform-default leak detection. Local cohort ASan/UBSan disabled leak detection
with `ASAN_OPTIONS=detect_leaks=0`; this limit does not apply to source CI.
[Compiled recipe CI](compiled-recipe-ci.json) is recorded separately.

Reproduction uses the build/compose/qualification entry points in the compiled
recipe checkout, with pinned source checkouts and the prior RF candidate as
inputs. Exact target commands and source/dependency hashes are retained in
`target-build.json`; source paths are task-local examples rather than downloads.
No firmware or candidate binaries are published by this evidence-only commit.
