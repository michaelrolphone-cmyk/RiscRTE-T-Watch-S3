# RF candidate packaging and the preserving 1.0.7 → 1.0.8 route

This is a separate candidate lane. It does not change, retarget or publish the
accepted 1.0.7 release, the frozen 1.0.6 midpoint, or the old latest-main builder.
It reuses exact accepted Runtime 0.1.41 native bytes without a native rebuild.

The installed origin is read from the accepted image itself: product 1.0.7,
Watch source `5c317f80b471d754111dbbe5a14fe97fd0dc377c`, full-image SHA256
`b039468858ab3cb5d1b53d843257e0e034d0a0b661ddaf3b74b59670519b0b2b`.
The later release merge commit is not substituted for the device cohort source.
`apps/rf-spectrum-native-custody.json` pins every reused native candidate asset,
including the actual native ELF used for strict target import admission.

## Inputs

First build a complete RF app artifact using `build_rf_spectrum_apps.py` and
the final immutable source profile. The Watch checkout must remain clean at
that artifact's exact source head. A standalone Waterfall ELF, a synthetic
metadata fixture, or an older profile archive cannot qualify this candidate.

The app archive contains all 22 target applications, their original/debug ELF
custody, source/compiler/dependency proofs, every rebuilt provider and licenses.
The packager overlays those exact verified files onto the accepted 89-file store.
All existing identities, grants, provider bindings and persistent owners remain
unchanged, except Waterfall's two new unused private storage grants. It omits
the obsolete HID shared-preferences migration record.

The default preserving route requires the hardware-accepted `bma423` with
`selectable` radio declaration and byte-identical board JSON. A `bma456h` profile
may use initial-only packaging; no accepted preserving origin is asserted for it.

## Commands

```sh
python scripts/build_rf_watch_candidate.py build \
  --apps-dir dist/rf-spectrum-bma423 \
  --runtime RUNTIME \
  --native-dir RUNTIME/dist/esp32s3-16mb-appdata-iq \
  --installed-system-apps ACCEPTED_SYSTEM \
  --mode paired --output dist/rf-watch-1.0.8-paired
```

`paired` is the default. Its output is `twatch-s3-cohort-1.0.8.bin`; the canonical
name and URL are required by the already-installed updater's catalog parser.
It contains exactly accepted native firmware followed by the new complete bootfs.
NVS and app-data are excluded. Never flash this payload at offset zero. The
instructions and proof explicitly label it as the preserving paired update.

Use `--mode initial` for an explicitly destructive initial image, or `--mode both`
to produce both distinct artifacts for the accepted board. Initial images are
named `twatch-s3-1.0.8-FULL-INITIAL-ERASES-DATA-<motion>.bin`. They are full 16MiB
images at offset zero and overwrite settings, credentials, Bluetooth bonds,
alarms, Points, all app-data and both banks. They are not preserving upgrades.
Future catalog publication also requires its canonical full-image alias; this
packager performs no publication and emits no release catalog.

```sh
python scripts/build_rf_watch_candidate.py verify \
  --bundle dist/rf-watch-1.0.8-paired \
  --runtime RUNTIME --native-dir RUNTIME/dist/esp32s3-16mb-appdata-iq \
  --installed-system-apps ACCEPTED_SYSTEM
```

Verification checks the exact artifact inventory, checksums, source/native
custody, embedded full app archive, installation wording, licenses, byte-level
store reconstruction and deterministic packing, and repeats strict target
graph/ELF admission. The installed System source is the exact accepted `f146d82d`
checkout, even when the new candidate uses a later reviewed adapter correction.
The bundle includes build/upgrade proofs and the full app archive; it does not
duplicate the native ELF or extracted bootfs tree.

## What the preserving proof executes

No preserving artifact is emitted until its actual target bytes pass:

1. Accepted-source and candidate self-admission through production Runtime0.1.41,
   including real target ELF structure and the accepted native export table.
2. Eleven negative graph/ELF cases covering namespace theft, changed hardware,
   old migration authority, missing preferences, excess grants and corrupt code.
3. Thirty-one native adapter scenarios using production `begin_cohort`, write,
   finish, step, activation, abort and boot/rollback paths. Cases cover pending
   source state, product/repository/version/revision gates, stale active-store
   hashes, cancellation and power interruptions, transport/flash corruption,
   uncertain native/store/journal writes, mount/cleanup failures, graph rejection,
   post-admission mutation and uncertain activation.
4. Fresh processes for pending candidate boot, rejection/rollback, source reboot,
   retry and modeled confirmed candidate restart. Every snapshot preserves the
   entire source pair/journal and nonuniform NVS/app-data sentinels byte-for-byte.

The raw flash bytes and read-only mounted file views derive from the same exact
SPIFFS payload. Production store/native hashing and graph/ELF admission run;
the host fixture models the IDF flash/VFS boundary, running-app state and bank
selection. It does not execute physical flash, network TLS, native SPIFFS
parsing, target instructions or actual device health confirmation. Those limits
are recorded explicitly, including the later confirmed-state restart model.

Temporary transaction storage is bounded: one 16MiB accepted source snapshot,
one reusable 16MiB result snapshot, the tested OTA, two extracted stores and
small host executables. No per-scenario full-image archive is retained. The
driver checks at least 60MiB temporary allowance plus 100MiB free for other work;
temporary snapshots are removed after the proof, preserving the proof JSON.

## Harness-only validation before full targets exist

```sh
python scripts/test_rf_watch_upgrade.py \
  --runtime RUNTIME --native-dir RUNTIME/dist/esp32s3-16mb-appdata-iq \
  --check-installed --output dist/rf-harness-proof.json
SANITIZE=1 python scripts/test_rf_watch_upgrade.py \
  --runtime RUNTIME --native-dir RUNTIME/dist/esp32s3-16mb-appdata-iq \
  --check-installed --output dist/rf-harness-sanitized-proof.json
python -m unittest discover -s tests -p test_rf_watch_candidate.py -v
```

This self-test reuses accepted ELFs with test-only RF metadata and a test source
identity. Its proof is labeled `accepted-harness-self-test-only`; it cannot
qualify a complete RF artifact or satisfy the candidate packager's full-target
requirement. Sanitized subprocesses disable LeakSanitizer, which cannot operate
under this execution environment's ptrace boundary; ASan and UBSan remain active.

Building or verifying a candidate performs no release, merge, publishing,
catalog update or device operation. Full target packaging and physical
qualification remain separate steps from implementing/testing this route.
