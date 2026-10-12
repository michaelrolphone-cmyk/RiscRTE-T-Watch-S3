# Files 1.5.35 lifecycle-overlay qualification

Status: exact public source and recipe qualified. Complete Watch admission passed.
X4 component intake is qualified; complete cumulative X4 settings/internal/SD
admission remains the responsibility of its separate compositor.
No firmware was flashed or delivered. No full image was written by this recipe.

## Exact sources

- [System source](https://github.com/michaelrolphone-cmyk/RiscRTE-System-Apps/commit/66282802bb498590fcbab4eba871ff40cc3ddafd): `66282802bb498590fcbab4eba871ff40cc3ddafd`, tree `5d588c4da9e4b5ba4f90021731022656940b87a4`
- [Target and Watch recipe](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/commit/2b1d73a012a2d6cb73d5b2ccb886077c7a70e189): `2b1d73a012a2d6cb73d5b2ccb886077c7a70e189`, tree `b0828e6f3a53f3475bcb745e9f25b9244edc57ad`
- [Source CI](https://github.com/michaelrolphone-cmyk/RiscRTE-System-Apps/actions/runs/38316434394): passed
- [Recipe CI](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/actions/runs/38316575232): passed, 21 regression tests

The complete Watch predecessor is the qualified LoRa handoff with SHA-256
`50356c81cc12456bea055f93e9035babe07f3eeaf5939f53d3d99740c2aaafc4`,
compiled recipe `5664da64e83a2a006d73773fadf966ef66b66ad7`.
The Files 1.5.34 component predecessor hashes are pinned separately in the recipe.

## Target evidence

- Watch Files ELF: 291,468 bytes, SHA-256 `915779e0a7098a8df3238b33648a6703e3958eddf736a1acd20169eb01062c47`
- X4 Files ELF: 496,348 bytes, SHA-256 `8214b21bc06222ef78b02e13ad39035adc7e7b67d8548ecd3ee173060ca64d7a`
- Both targets preserve every selected feature and original font. The only added selector is `PORTABLE_TEXT_INPUT_POLICY`.
- Watch disabled-policy ELF equals its selected predecessor byte-for-byte.
- X4 disabled-policy executable, allocated data, relocation and all other section bytes equal the selected predecessor. Only eight enumerated compiler-local numeric suffixes in non-allocated `.strtab` differ. Independent loader-metadata-v3 compaction yields identical 312,568-byte ELFs, SHA-256 `0520817afcfc0094842265577fc72cf08e9a131400a00406336242c8d5eb65f1`. Production X4 files retain their original uncompacted format.
- Actual Xtensa entry frames peak at 240 bytes for the Watch selection and 304 bytes for X4, including its unchanged `app_main` frame. Static draft/filter/state/client/checkpoint storage is 128/64/144/48/8 bytes.

## Complete Watch cohort

Normal and ASan/UBSan admission receipts are byte-identical, SHA-256
`64b10bce800135ccb1a4305a29aa95ca1ca65aa9528edf02258787848a08383e`. All 55 ELFs and 113 files are admitted, with two free
SPIFFS blocks. Native firmware, boot bytes, capability grants, unrelated ELF
bytes, shared input hosts and RF 0.3.4 remain unchanged. RF 0.3.5 is excluded.
Only Files ELF/version and cohort source identity change substantively.
Twelve explicitly allowlisted unsigned manifests receive deterministic,
lossless whitespace packing; duplicate keys, non-finite numbers, scalar-type
changes, signed metadata and other semantic changes are rejected.

- Store SHA-256: `3a0058804de392bc6426ae47251f01a72efcabac7395dab5f7551de263813ceb`
- Streamed full-initial image SHA-256: `bbbb843321fe96687946bbf489e8486cb3ce4917a44441aed82eabc1c4cd3317`
- Full-initial size: 16,777,216 bytes; not materialized; erases user data if flashed

The X4 intake overlay changes only `file_browser.elf` and `file_browser.json`
over the exact settings predecessor receipt
`ecebf457500d407241aefe23c7354ca5a92d0b1731933f028b74a290d565747a`.
It preserves the other 104 internal files, native firmware and its compile
identity, all SD bytes, settings, OBD, grants and RF. It does not replace the
compositor's other System source selections.

## Source and verification boundaries

Source checkpoint SHA-256
`83f84bd02e8cdb3d4e3a48c499c846b602e7fbf97129e62621986a0848fdcbab`
binds 44 normal/sanitized policy cases, 144 normal/sanitized legacy workflows,
and 53 rendered-frame comparisons. The independent reviewer reported 114
probes passing; original terminal logs were not saved, and preserved
reproduction sources and the review receipt state that limitation.

Host tests and ELF structural checks do not execute target instructions or
qualify physical input, display, radio or power behavior. Entry-frame inspection
does not prove dynamic peak call-chain stack usage.

The accompanying `qualified-receipt.json` binds all exact component, source,
CI, predecessor, target-stack, flag-off and Watch cohort receipts. Its local
final handoff SHA-256 is `6df57f7a37405f5410fd49bd24f557ee5f8c2543948df1321190ebcb574f50dd`.
