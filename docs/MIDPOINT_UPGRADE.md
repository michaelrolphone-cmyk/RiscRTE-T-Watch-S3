# Data-preserving midpoint upgrade

This is the bounded route for the installed Watch image from source
`27fba6f26a64501eadd308d4b1e7225c712ea50b`, full-image SHA-256
`2225261601729774c7d0d42a88ab1a705c55aa856097af292dce9fa06dd659bf`.
Its cohort is 1.0.2, Runtime is 0.1.33, and its exact 73-file store is pinned in
`apps/midpoint-origin-baseline.json`. That original BIN is a **read-only custody
input**, never an upgrade payload.

## Required route

1. Install the existing native-only 1.0.3 bridge, Runtime 0.1.34, through the
   existing Firmware Update path. Its native SHA-256 is
   `00f5b15ef3701125557e3c5641edab3bcedd79bf53c47a2318c1899cc4257e38`.
   The transaction copies the midpoint store unchanged to bank 1. The cohort
   remains midpoint 1.0.2; never rewrite its source identity to pretend it is 1.0.4.
2. Restart and verify healthy Clock. Then install the separately built,
   midpoint-origin Watch **1.0.6** paired cohort. It carries the final ordinary
   1.0.5 app/provider bytes and Runtime 0.1.35, with only the two metadata files
   described below changed. Runtime 0.1.34 installs this final pair into bank 0.

Both stages preserve the NVS and app-data partitions and keep the preceding
complete native/store pair available for rollback until health confirmation.
Full initial images are destructive provisioning inputs. Never flash one for
this upgrade, write an empty app-data image, or serial-flash an OTA at offset zero.

Frozen 1.0.4 and ordinary 1.0.5 cohorts reject this exact midpoint. Their migration
origin is a different source revision. The unchanged 1.0.3 bridge does not change
that origin. A reflash or a Runtime policy relaxation is unnecessary.

## Why a separate 1.0.6 product

The installed System Apps updater at
`2d16d9dfa7abc50ce916eebc11d81423adef0000` accepts only the canonical
`twatch-s3-cohort-{version}.bin` filename under `firmware-v{version}`.
A `-midpoint` suffix is rejected. Reusing 1.0.5 for different bytes would collide
with the ordinary 1.0.5 path. The exact midpoint profile therefore uses
`twatch-s3-cohort-1.0.6.bin` under `firmware-v1.0.6`.

The normal 1.0.4 → 1.0.5 builder and its accepted inputs remain unchanged. This
profile does not claim that the midpoint payload also admits a 1.0.4 installation.
Any eventual catalog publication must select the reviewed source-specific route;
these tools do not publish or switch a live catalog. Catalog tests use temporary
parser fixtures, not publishable provisioning-image release records.

## Bounded metadata

The variant builder consumes a fully built ordinary 1.0.5 bundle. It independently
rechecks its frozen source, native provenance, Runtime requirements, ELF/store
representations, exact file hashes, and unchanged ordinary packaging policy.
Every app ELF, provider ELF, manifest, hardware declaration and permission row is
then retained byte-for-byte. Only these files differ:

- `cohort.json`: target product version becomes 1.0.6; native identity, source
  revision and all other fields remain tied to the standard candidate.
- `boot.json`: source-bound migration is from midpoint 1.0.2 at the exact source
  above to 1.0.6. New Waterfall, BLE Touchpad and BLE Buttons share only the
  already-universal API-1 settings namespace 1. Existing private ownership and
  app-data bindings do not change.

The builder rechecks every midpoint app/provider owner against the actual pinned
midpoint, in addition to checking the ordinary 1.0.4 → 1.0.5 policy. Both the
installed 0.1.34 Runtime and target 0.1.35 Runtime must admit the result using their
own native ELF export sets. Runtime migration grammar and policy are untouched.

## Build after the final ordinary cohort is ready

Use clean checkouts and the exact frozen native/bundle inputs. The ordinary
candidate must be built from the same Watch commit as the variant builder:

```sh
python3 scripts/build_midpoint_watch_cohort.py \
  --installed-bin /inputs/twatch-s3-tap-midpoint-27fba6f2.bin \
  --previous-bundle /inputs/accepted-1.0.4/sdr-upgrade \
  --candidate-bundle /inputs/final-1.0.5/next-watch-cohort \
  --previous-runtime /sources/runtime-0.1.34 \
  --previous-native-dir /inputs/accepted-1.0.4/native \
  --runtime /sources/runtime-0.1.35 \
  --native-dir /inputs/final-1.0.5/native-runtime \
  --output /outputs/midpoint-1.0.6
```

The result is native+bootfs only, the exact extracted store, licenses, requirements,
checksums and `midpoint-watch-build-proof.json`. No full image is emitted.

## Verify the final exact artifact

```sh
python3 scripts/test_midpoint_watch_upgrade.py \
  --installed-bin /inputs/twatch-s3-tap-midpoint-27fba6f2.bin \
  --previous-bundle /inputs/accepted-1.0.4/sdr-upgrade \
  --candidate-bundle /inputs/final-1.0.5/next-watch-cohort \
  --midpoint-bundle /outputs/midpoint-1.0.6 \
  --installed-runtime /sources/runtime-0.1.33 \
  --previous-runtime /sources/runtime-0.1.34 \
  --previous-native-dir /inputs/accepted-1.0.4/native \
  --runtime /sources/runtime-0.1.35 \
  --native-dir /inputs/final-1.0.5/native-runtime \
  --installed-system /sources/system-apps-2d16d9df \
  --output /outputs/midpoint-proof
```

Repeat with `SANITIZE=1 ASAN_OPTIONS=detect_leaks=0` and a fresh output directory.
The proof covers exact installed boot admission, bridge admission of every retained midpoint ELF, installed/target cohort
admission, wrong-origin/authority rejection, positive and negative installed
catalog parsing, nonuniform NVS/app-data sentinels, immutable rollback pairs,
interrupted downloads, corruption, cancellation, uncertain activation, candidate
rejection, fresh-process reboot and retry. The final transaction starts from the
bridge's actual selected bank 1, rather than an invented bank-0 source.

`--check-fixture` can replace `--midpoint-bundle` to check this test infrastructure
against historical standard candidate bytes. It emits only evidence and temporary
flash fixtures, marks `final_artifact_acceptance: false`, and is **not final
artifact acceptance**. All final fixed bytes still require the full command above.

Source-only tests:

```sh
python3 -m unittest discover -s tests -p 'test_*watch_cohort.py'
```

Host proofs do not execute target instructions, real SPIFFS, TLS, physical flash,
physical power loss, or actual default-app health confirmation. They do not
qualify the alarm/Hybrid hardware fix or authorize device access, publication,
merge, delivery, or installation.
