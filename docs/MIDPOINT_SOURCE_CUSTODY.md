# Historical midpoint derivation closure

The source-only Clock closure repair restored the legacy Wi-Fi and updater
lanes in [main CI 38757312080](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/actions/runs/38757312080).
The newly reachable low-battery lane then found a separate historical
publication defect: the 1.0.6 midpoint publisher compared live helper files
against the immutable 9c8ecf7e acceptance. Four live helpers had legitimately
evolved: `current_cohort.py`, `current_bootfs.py`, `current_flash_layout.py`, and
`read_only_spiffs.py`. Its transitive imports also came from the live tree.

`custody/midpoint-1.0.6` now owns 38 exact inputs from
`9c8ecf7e2e20bdda24e6f5fb97273ffd7797a94a`, including the complete 28-module
Python import closure, original metadata, catalog harness and SPIFFS generator.
Every file retains its original bytes and public Git blob identity. The complete
inventory and provenance file are hash-pinned. The original 17 derivation
identities in `release/midpoint-test-acceptance.json` remain unchanged.

The midpoint publisher selects this isolated graph. Local imports, including
lazy imports inside functions, resolve to the same frozen graph without
replacing live entries in `sys.path` or `sys.modules`. Explicit file-loader
imports compile original source directly rather than consuming or generating
bytecode caches in the frozen tree. Current product helpers continue using
their current source and expanded-layout support.

The original hosted ZIPs were independently recovered and hash-verified:

| Role | Artifact | SHA256 |
| --- | ---: | --- |
| Bridge | 11406816292 | feb7bba400a467013d85cf63ed77d4972fbe7d13a59dd907007d344c902b39f5 |
| Ordinary | 11439655989 | 14185f0757caae8857369d543698ddc0e9321faff70b96e3e9698db577f04a0e |
| Native | 11439576096 | ef1008a6518adb42ae02569b6bd141b03925f34bd8405838a4fa6432087f2a78 |

To run the existing complete derivation test, place those unchanged ZIPs under
`MIDPOINT_ARTIFACT_DIR` as `bridge.zip`, `ordinary.zip`, and `native.zip`, then run
`python -m unittest discover -s tests -p 'test_midpoint_*.py' -v`.
The suite verifies every frozen derived asset and index identity against the
original acceptance. It also retains all publication refusal and transaction
evidence tests. Additional custody tests cover changed, missing, added and
rehash-forged inputs, live import-cache poisoning, lazy imports, mutation before
module execution, and generator inventory preservation.

This repair does not change the original acceptance/evidence, expected firmware
hashes, any current app or driver source, or any released firmware/tag/asset.
It does not publish the historical midpoint firmware or access a device.
