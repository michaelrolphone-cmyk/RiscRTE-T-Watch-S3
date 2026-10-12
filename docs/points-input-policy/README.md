# Later-build Watch Points lifecycle overlay

This independent recipe prepares Watch Points 0.6.14 from the exact selected
0.6.13 predecessor. It does not change tonight's sealed Watch or X4 selectors,
candidates, Files artifacts, native firmware, grants, storage format, or RF
selection. X4 Points 0.6.17 remains blocked on unresolved source provenance.
RF 0.3.5 remains excluded from this overlay; its separately reauthorized publication does not change these cumulative bytes.

The exact public Productivity repair is
`3c5930ba5715844055bb7853dd4fe9a02cbde4db` (tree
`41bade4fe8cd08ef10579b8e691a8017b65762cc`). Local provisional outputs are explicitly labeled
and cannot enter public qualification. The only added target option is
`-DPORTABLE_TEXT_INPUT_POLICY`; every inherited option, font, generated catalog,
profile, and source dependency is checked. Generated include paths are relocated
without other content changes. The selected Watch compiler is GCC 8.4.0,
esp-2021r2-patch5.

## Qualification gates

1. Build component only with `scripts/build_points_policy.py`. Pass exact
   System, Utilities, Productivity, Runtime SDK, and Watch profile roots. Use
   `--provisional` only for local preparation; provide a fresh output directory.
2. Run `scripts/inspect_points_target_stack.py` against the build and
   `scripts/test_points_policy_flagoff.py`. Disabling only the policy flag must
   reproduce unchanged Points app sources compiled against the same current
   dependencies byte-for-byte. Separately report the selected 0.6.13 raw-byte
   comparison: the selected Watch scene host has no navigation dependency, so System
   9957e7c9 restores the original app-local PMU Back fallback. The isolated
   flag-off and exact selected-predecessor comparisons are reported separately.
3. Report the exact ELF growth and page demand against the sealed Files union
   before additional packing or any size workaround.
4. Run `scripts/assemble_watch_points_policy.py` against the hashed cumulative
   Files handoff, candidate, unchanged native ancestor, and Runtime profile.
   The candidate is a separate later-build directory. The app ELF, version
   metadata, cohort source revision, and any strictly lossless allowlisted
   unsigned JSON whitespace are the only permitted differences.
5. Repeat assembly with `SANITIZE=1 ASAN_OPTIONS=detect_leaks=0 --verify-only`.
   Require byte-identical normal/sanitized complete-cohort admission receipts:
   55 ELFs, 113 store files, 24 app policy rows, zero hardware/storage calls,
   and at least two free SPIFFS blocks. The full-image hash is streamed from
   immutable ancestor bytes; no full image is written.

Duplicate JSON keys, non-finite values, decoded scalar-type changes, signed or
unlisted metadata rewrites, boot authority changes, dropped features/fonts,
and reducing the two-block reserve are rejected. A separately proved metadata
gap pack moves only non-allocated tail sections and the section-header table
into existing unmapped file padding. Program headers, allocated section bytes,
addresses, alignments, imports, exports and relocations remain identical.
The existing loader-evidence comparison must pass before the packed file is used. Capacity failure prints exact
component/payload deltas and geometry-derived object-page shortfall. It does
not authorize or apply a code-size workaround.

Host lifecycle tests and source review remain separate from target structure
and complete-cohort admission. Entry-frame measurements do not establish
peak dynamic call-chain stack use or physical device behavior. No flashing,
delivery, deployment, or hardware qualification is performed by this recipe.

The first recipe 854266b2 was held after its host fixture incorrectly supplied
a fifth navigation dependency. This successor uses the four deployed scene
dependencies and the original independent app-local PMU bridge. System source
9957e7c975f7b57ce9ea50d57b13c1d9bb75cf43 restores only that local attention path;
shared navigation stays host-owned. The corrected full host suite passes all
92 workflows. Independent correction review remains a separate final gate.
