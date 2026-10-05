# Watch 1.0.1 stable product

Watch **1.0.1** promotes the exact complete 16 MiB image from accepted source
`3e703ab7e8ef506394fb24c6862dc8bfafddc475`, successful CI run
[37276394351](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/actions/runs/37276394351).
All nine image prerequisite/final jobs passed, including execution of the actual
final store through Runtime in normal and ASan/UBSan configurations. Every one
of its 58 stored files, all six flash components, and the complete install ZIP
are hash-verified. Acceptance is on software CI; no new hardware qualification
or device operation is claimed.

The final current cohort contains 15 applications, the volume-aware alarm/CUE
service and two update providers. It includes the confirmed crown-state repair,
Spectrum 0.2.2 corrections and all eight Utilities PRs. Owning source commits are
integrated in their respective default branches and independently tagged:
System Apps `13f32d3e`, Utilities `9f2e6022`, Productivity `edd754ab`, and existing
Runtime `0fa8c576` / 0.1.16. Current Clock/default 0.8.1 use the explicit
`apps/clock/current-manifest.json`; historical custody lanes keep their original
0.8.0 manifests and source pins.

The seven firmware asset types from 1.0.0 are retained: the directly flashable
`twatch-s3-launcher-1.0.1.bin`, original updated install ZIP, `FLASHING.md`,
`SHA256SUMS`, `product-provenance.json`, `release-record.json`, and
`release-index.json`. All 15 configured app ELFs/manifests are also published as
independent Watch-configuration releases, and the index references 17 verified
physical-driver packages. Existing immutable records are reused only when the
complete package bytes/manifests match exactly.

BIN SHA256: `c9acc4bf2a4070a97fb1a8090d584e68e6ad8fe411d9cef7d4c4135ce672e7c1`.
The original frozen ZIP is `twatch-s3-main-0.8.1-3e703ab7-install.zip`.

**Flashing replaces all 16 MiB, including both banks, settings, credentials,
alarms, Stopwatch and Points records. Back up first.** This is a full migration
image. Publication never flashes a device.

Known limitation: the observed five-minute Hybrid wake issue remains deferred
to the next increment. Its isolated recovery implementation is excluded from
this release. Physical microphone response, audio loudness, touch behavior and
power consumption remain separately unqualified.

The canonical frozen source/artifact/version manifest is [product.json](product.json).
The original 1.0.0 manifest remains byte-for-byte preserved below.

# Historical Watch 1.0.0 baseline

The owner accepted the exact integrated 0.5.2 build on 2026-10-04 and authorized
contributing merges, publication, and a separate Reader-style release index.
Product version **1.0.0** promotes those same bytes. It does not renumber Clock
0.5.2, Runtime 0.1.6, or shared packages. The source-controlled product identity
and accepted artifact/source pins are in [historical product manifest](history/product-1.0.0.json).

The release is `firmware-v1.0.0`, with directly flashable
`twatch-s3-launcher-1.0.0.bin`. Its SHA-256 remains
`6f0cba6da17fce769d03807aefce44b0e5fc445d349b8b7dc0f6782d376d80c5`.
The original 0.5.2 flashing ZIP is preserved unchanged for custody and recovery.
Flashing at 0x0 replaces the lower 8 MiB including settings and saved Stopwatch
state; upper 8 MiB is untouched. Publication does not flash any device.

All seven exact configured applications are independent releases in this Watch
repository, including the directly downloadable **default.elf** core and its
matching default.json. App versions, compiled Watch configuration, licenses,
shared owning-source pins and exact bytes are retained. These are the ELFs inside
the accepted Watch image, not the differently configured generic shared builds.
The existing driver publisher produces independent immutable versioned packages.
The product publisher downloads them and checks every package against accepted
CI; the six installed driver ELFs/manifests must match the image exactly. Other
optional drivers are cataloged without claiming hardware qualification.

The dedicated [`release-index` branch](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/tree/release-index)
contains `release-index.json`. It follows Reader's schema 1: firmware object,
apps array, drivers array, immutable version/tag/asset/url/size/SHA-256 records,
plus component manifests. Updates are monotonic, reject same-version content
changes, preserve unrelated entries, and use a non-force branch push after every
referenced release is public and download-verified. Reader itself is untouched.

`Publish accepted Watch product` validates on the release PR and publishes only
from the repository's current default branch, after the existing driver
publication workflow completes successfully (or explicit manual dispatch). It
shares the driver's publication concurrency group. Assets are uploaded to drafts, downloaded and
hashed before publication; interrupted drafts resume only with identical bytes.
Published versions are never overwritten. Future product versions need a new
accepted product manifest and exact source/artifact evidence. Historical Actions
artifacts may expire; the published provenance ZIP remains the permanent source
of these released bytes. Missing frozen inputs fail closed rather than rebuild.

The old custody ZIP's pending-hardware text is historical build-time evidence.
Product provenance separately records owner acceptance of the exact integrated
Watch. This is not blanket qualification of all optional peripherals, CAM/X4,
power consumption, or future component builds.

## Frozen main-style products (schema 2)

The publisher also supports reviewed, CI-accepted full 16 MiB main-style images.
This support does not itself select or accept a new release. `product.json` is
still the existing 1.0.0 manifest until a separately reviewed freeze supplies
all final identities. The unchanged historical manifest is retained under
`history/product-1.0.0.json` for regression checks.

A schema-2 freeze must provide:

- The product version/tag, acceptance date, and
  `acceptance: {"kind": "ci-accepted", "hardware_qualified": false}`.
- Exact Watch commit and tree, Runtime commit and embedded version, and every
  source generation in `deployment_sources.audio`, `.points`, and `.update`.
  These are the complete source maps from the accepted Watch checkout, including
  different historical generations that remain compiled into the image.
- Exact BIN/install-ZIP basenames and SHA-256 hashes, 16 MiB capacity/size, offset
  0x0, and the final store-file count (at least 58).
- Four Actions artifact pins in `artifacts`: `main` (flashable image), `audio`
  (update integration), `points` (Points integration), and `drivers` (complete
  driver packages). Each needs repository, run ID, run attempt, artifact ID,
  exact artifact name, source SHA, and download SHA-256. All must originate from
  the same completed, successful Watch CI attempt. The two deployment artifacts
  also need the exact inner common archive path in `bundle_member`.
- `component_versions`: every top-level embedded application, plus `runtime`.
  This is a complete inventory, not a seven-app allowlist. The publisher discovers
  applications from the frozen manifests and requires the maps to match exactly.
- `driver_versions`: every package ID/version in the complete physical-driver
  catalog. `embedded_driver_versions`: every store directory containing a driver
  manifest, including alarm/update services absent from that catalog.

The nine main-image dependency jobs, including `latest-main-image`, must all
pass for the accepted attempt. Download additionally verifies live repository,
workflow, head, artifact identity, creation window, expiration, and exact hashes.
Missing/expired inputs or incomplete placeholders fail closed; there is no
rebuild or fallback to a different source/artifact.

Staging reads the untouched BIN's SPIFFS store with the bounded read-only decoder.
It verifies the complete store inventory, paired component layout/hashes, erased
gaps, app ELF/manifests/versions, all embedded driver/service versions, source
maps, license custody, and exact installed physical-driver package bytes. It
copies the original install ZIP unchanged. Product promotion renames only the
standalone BIN asset and does not edit a byte of any embedded component.

The firmware release continues to have exactly seven top-level assets:
`FLASHING.md`, `product-provenance.json`, `release-index.json`,
`release-record.json`, `SHA256SUMS`, the product BIN, and the original install ZIP.
The generated warning states that the entire 16 MiB is overwritten, including
both banks, settings, Wi-Fi credentials and saved application state. CI acceptance
is recorded separately from pending physical verification. No device is accessed.

Run the publisher safety suite with:

```sh
python -m unittest discover -s tests -p 'test_watch*product.py' -v
python scripts/publish_watch_product.py download
python scripts/publish_watch_product.py stage \
  --accepted-watch PATH_TO_EXACT_WATCH --runtime-source PATH_TO_EXACT_RUNTIME
python scripts/publish_watch_product.py verify
python scripts/publish_watch_product.py preflight
```

`--config PATH` selects an explicitly prepared manifest for local review. `stage`
requires a new output directory and clean, exact source checkouts. It only reads
them. The frozen input archives remain in the staging artifact so verification
reconstructs every expected release payload independently of the publication
plan. The `preflight` command reads remote tags/releases/index and downloads
existing assets; it creates no release, tag, upload, or remote index change.

Before the first release write, publication checks the **entire** planned index
and all existing app releases. Same-version byte, manifest, source-provenance,
license, or record collisions fail closed. Existing records are not silently
rewritten or treated as interchangeable. This includes a changed contextual
`included_in_accepted_bin` flag on an otherwise unchanged driver-index record.
Resolve collisions through an explicit reviewed component/reuse plan before
freezing inputs; do not change an accepted manifest version after the build.

For identical physical-driver packages, `reused_driver_records` may explicitly
pin an existing full driver-index record by driver ID. The publisher compares
immutable identity/version/asset/size/hash and the full package manifest with the
frozen artifact, preserves the entire original record without changing source or
historical inclusion fields, and requires that exact record in the live index.
It downloads the public package byte-for-byte (including its source manifest),
checks the published release record, and verifies release/tag source provenance.
Any actual package, manifest, source-record or identity mismatch fails closed.
No old tag, asset or record is overwritten. Firmware product provenance separately
records `installed_physical_drivers`, which is authoritative for this product's
actual installation; historical component-index inclusion flags retain their
original context. App reuse is not implicit or supported by this mechanism.
Draft upload/download verification and final non-force monotonic index updates
retain the existing immutable publication protocol.

When the final image includes the reviewed current-apps overlay, schema 2 also
requires the fifth artifact `current-apps`, named
`twatch-current-apps-<exact Watch SHA>`, from that same CI attempt. Its exact
`current_apps_configuration` must equal the accepted checkout's
`apps/current-apps-sources.json`, the artifact's `source-profile.json`, and its
build record. The four owning repositories/commits, all final application
versions, and alarm-service version are checked against the final image pins.

That artifact contains the deterministic `current-apps.zip` plus identical loose
copies of its members. `current-apps-build.json` records the exact files, source
configuration and final boot policy. The main image's `current_apps_overlay`
contains the full `build_record`, its `build_record_sha256`, the inner ZIP's
`archive_sha256`, and disjoint `files`/`preserved_files` maps that cover the entire
final store. Every map entry is `{size_bytes, sha256}`. Allowed changed payloads
are all final apps (including both Clocks), the alarm and two update-service
providers, and boot.json. Historical Points/Clock evidence remains unchanged.
A separate current-apps `clock` record proves the final pair: current Watch SHA,
all current source pins, paired boot confirmation, four exact file hashes,
current Points header hashes matching the service, and safe Watch-relative source
file hashes. Staging checks those source bytes against the accepted Watch checkout. Current
license and source evidence is retained alongside the historical lane evidence
in independent app releases. The publisher rejects a final overlay with no
matching pinned artifact, or an artifact with no final overlay.

Publication rejects an external review-only `--config`, uncommitted canonical
product bytes, or a dirty tracked release-source checkout before remote writes.

### Integration gates and known limitations

Staging, stage verification and publication require the accepted Watch commit to
be a real Git ancestor of the release-source commit (`git merge-base
--is-ancestor`). Missing history or an unmerged/squashed PR-only candidate fails
closed. If squash integration discards the accepted commit, freeze a new image
from the integrated source rather than relabeling the old candidate.

Final read-only preflight independently queries GitHub for each current-app
owning repository's actual default branch (System Apps, Utilities, Productivity
and Runtime), resolves its exact current head, and compares the pinned source
commit to that head. The source must be the compare merge base with status
`ahead` or `identical` and zero commits behind. Config claims, tags alone and
successful CI are insufficient. All resolved default names/heads are checked
again before returning; moving defaults require a fresh preflight. The checked
heads, source commits, compare status and immutable comparison URLs are emitted
as JSON in preflight/publication logs before release writes. Publication also
rechecks the accepted Watch graph against the exact release commit verified as
the current Watch default head. These live proofs do not rewrite staged assets.

Schema 2 supports optional `known_limitations`, a list of up to ten nonempty,
single-line strings (500 characters each, 4,000 total). Any limitations are copied
into `FLASHING.md`, the firmware release notes, and product provenance. They are
release-specific data; no particular defect or deferred repair is implied for a
future product when the list is absent.
