# Historical Clock source closure

The historical Wi-Fi and paired-update integration builds retain the delivered
Clock bytes recorded in `apps/wifi-preserved-elf-baseline.json` and
`scripts/update-preservation-baseline.json`.

## Diagnosis

The broad driver workflow at cumulative source
`2c00363b6371276df087f71bea5b9a89a1d20e44` failed those byte-preservation gates:

| ELF | Bytes | Required SHA256 | Observed SHA256 |
| --- | ---: | --- | --- |
| clock.elf | 832736 | 51a6370952d0823e224976b9b59628f0a76f4bd10c8cdf8b531aa636e49bc72a | fae40f56f424c96375d3b8c00751c2ee03246b3be4c3e0392b2eeaaf0fe3a8f9 |
| default.elf | 832352 | b02820f75f0381ee14eb919630ecdd0a0b1649f6ec671941a80a5df97b018909 | ad859e9c128fb7f93103f0085409187be6238c20a464a2150e3d1faebb7dfa43 |

The old `legacy_clock()` implementation copied the live `apps/clock` tree and
overlaid only seven frozen source files. `launcher_touch.h` remained live.
Commit [b0da83dd](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/commit/b0da83dd10dc26fb7b13042a58183cef263d30c0)
introduced the current Home capture/replay sampler for Watch 1.1.20 on October 12,
2026. That legitimate current-Home change therefore also entered historical
Clock compilation. It precedes the 1.1.37 source `cf038ba6` by 43 commits; the
1.1.38 and 1.1.39 commits did not change the legacy source, recipes, pins, or
preservation expectations.

An isolated replay with the pinned Xtensa GCC 8.4.0
`crosstool-NG esp-2021r2-patch5` compiler reproduced both observed hashes.
Changing only the inherited touch header to the original frozen source restored
both required hashes at the same sizes. A separate replay of the complete
original Clock tree restored the same required hashes.

## Source authority and repair

All 130 files in `custody/sleep-prefix/PROVENANCE.json` are verbatim files from
[2a4fbae8fb2425bf830c302863a5e195106e77c9](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/commit/2a4fbae8fb2425bf830c302863a5e195106e77c9),
the snapshot's existing source authority. This includes the entire original
Clock tree, generated assets, app SDK, and the already-frozen driver inputs.
The complete inventory and every file hash are verified, and the provenance
document itself is hash-pinned by `legacy_inputs()`. Rehashing altered source
cannot silently admit it.

The original touch header's SHA256 is
`1742842453178836c8d24e0810575ffc3ee4cb47ffffc89296135a45b0891185`.
Its public Git blob is `9ce5c1303d3b6f9f0645e57b604f86cb4752dd27`.
The current Home header's diagnostic SHA256 was
`f1d022f9521b0a75782d9fe95629c7908fadbf88e1a779d38ef1b153f46fb9cb`.

Historical builds now materialize only this frozen Clock tree. Repeated builds
remove stale generated inputs. Clock effects, projection, navigation, app SDK,
and shared compatibility comparisons select the frozen source. The
`current=True` build still selects live current Home source and SDK.
External System Apps, Utilities, Productivity, and Runtime inputs retain their
existing exact repository pins. Every delivered ELF hash expectation remains
unchanged. Release tags and existing assets are outside this repair.

## Regression checks

`tests/test_legacy_clock_custody.py` checks the frozen source identity and
inventory, live-source isolation, stale-output removal, current/frozen compiler
routing, changed-source rejection, rehashed-source rejection, and unchanged
target expectations. The broad driver workflow runs this suite.

Target qualification runs the existing complete `build_wifi_apps.py` and
`build_update_apps.py` recipes against their exact dependency commits, retaining
all original preservation assertions. Source-contract qualification also covers
motion, PMU, panel, native-faces, and launch-brightness contracts.

Local qualification on the repaired source passed:

- All 130 frozen blobs independently matched the original public GitHub tree.
- Both full app builders, including original ELF preservation gates.
- All 17 current driver packages and the three frozen driver packages.
- All eight Wi-Fi deployment archives and seven authority tests.
- All eight paired-update archives, 25 update tests, and six store-input tests.
- Seven closure tests, four motion, five panel, and seven PMU custody tests.
- Native-faces: 128 exact-store mutation rejections; launch-brightness: 196.
- Wi-Fi bundle suite: 11 passed; the SPIFFS-tool round trip and pinned Runtime
  CI-artifact checks were not run locally because those inputs were absent.

The paired-update default ELF intentionally includes boot confirmation and has
SHA256 `4ec17c9115f22093bb460e68fdc6b3d28396020f48ff6cd8c2c8f0c519a69197`;
its preservation policy already excludes that default from the Wi-Fi baseline.
The paired-update Clock ELF matches the original `51a63709...` expectation.
Physical-device behavior and remote CI are separate verification stages.
