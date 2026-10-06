# Guarded publication of the exact midpoint 1.0.6 route

This support publishes no release on a branch push, PR, CI success or merge.
The two stages remain separate manual operations. Publication does not install
anything or establish device health.

The only installed-Watch route is the existing **Firmware Update** application:

1. Native-only bridge **1.0.3**, Runtime **0.1.34**.
2. A real operator-confirmed healthy restart, including Clock and retained data.
3. Exact-midpoint paired cohort **1.0.6**, Runtime **0.1.35**.

This route is only for source `27fba6f26a64501eadd308d4b1e7225c712ea50b`.
The unchanged bridge retains that source and its 73-file store. Frozen 1.0.4 and
ordinary 1.0.5 do not admit this midpoint. Do not use their second-stage commands
or relabel the installed cohort. No Runtime policy is relaxed.

## Frozen inputs and explicit derivation

Payload source is `9c8ecf7e2e20bdda24e6f5fb97273ffd7797a94a`. A later publisher
commit is an ancestor-preserving descendant, not a new payload source.
`release/midpoint-test-acceptance.json` freezes the original hosted inputs from
successful driver-contract run **37516805328**, attempt **1**:

- Ordinary 1.0.5: artifact **11439655989**, original ZIP SHA-256
  `14185f0757caae8857369d543698ddc0e9321faff70b96e3e9698db577f04a0e`.
- Native 0.1.35: artifact **11439576096**, original ZIP SHA-256
  `ef1008a6518adb42ae02569b6bd141b03925f34bd8405838a4fa6432087f2a78`.
- Original bridge/scaffold input remains artifact **11406816292** from run
  **37448348806**, attempt **1**, governed by unchanged
  `release/sdr-test-acceptance.json`.

There is **no hosted midpoint artifact**. The publisher derives the 1.0.6 store
deterministically from the original ordinary ZIP using the unchanged source-bound
metadata transformation. Only `boot.json` and `cohort.json` differ. Native, app,
provider, manifest and license bytes remain exact. The resulting OTA is byte-for-
byte equal to the independently exercised final candidate:

- `twatch-s3-cohort-1.0.6.bin`: **6,519,568 bytes**, SHA-256
  `b6134bcaf5fed3cd954ea800a58ace62fe76715f965c79435baf34668309aa6c`.
- Store SHA-256:
  `60e5b8d2eff7b42e8eddc8bb24a9794bd25db30807074273e4d38b3ba4ccbcd5`.

The committed normal and ASan/UBSan midpoint reports each contain **128**
transaction/reboot/retry checks and **19** admission rejections. Their execution
receipt records the actual command, explicit sanitizer environment, successful
`set -e` completion and independently inspected sanitizer linkage. Identical
normal/sanitized report hashes are expected; report filenames alone are not mode
evidence. The original reports are preserved unchanged. The original parser was
normal-only, so this publisher separately executes the **real final catalog**
with both normal and ASan/UBSan installed-parser binaries.

Read-only connector snapshots support initial freezing where a local `gh` login
is unavailable. They are identified as snapshots. Every remote preflight and
publication rechecks live run/attempt status, artifact identity, expiry, digest
and creation interval with the workflow's token. Expired or unavailable artifacts
block publication; a local rebuild or repacked ZIP is never substituted.

## A truthful initial-only asset

The current catalog requires a canonical top-level launcher record. The new
publisher creates an actual **16 MiB** initial-only image, not the synthetic
envelope used by the route parser tests. It uses verified native candidate
components and the exact derived 1.0.6 store. The scaffold is the frozen 1.0.4
initial image, SHA-256
`d4a1f41035e272adb0ec5d0c64b63835c771cc773a19805463cfe7ab2eb3c67e`.

Bootloader, partition table, empty app-data, inactive bank, gaps and unrelated
regions must match the scaffold. Fresh bank0 VALID metadata binds the final
native/store hashes. The final asset is `twatch-s3-launcher-1.0.6.bin`, SHA-256
`8b683308ab763d62bfd81acab10e4ab6b03f16b1b8ac78cecceb131fe8758c23`.

**This full image is destructive initial provisioning only. Never flash it to
upgrade an installed Watch.** The updater selects the nested OTA URL containing
only native + bootfs. No NVS, app-data, bootloader, partition or initial journal
is included in that OTA. Never serial-flash an OTA at offset zero.

## Default-branch integration requirement

The publisher, canonical acceptance and evidence must be reviewed and committed
on the current default branch. Source 9c8ecf7e must remain an ancestor; squashing
away the accepted source fails the guard. The existing product manifest and old
SDR publisher/acceptance remain unchanged.

Merge authorization is separate. Although SDR and midpoint publication are
manual-only, the repository's existing default-branch driver publisher and its
chained frozen-product workflow can run after a merge. Review those effects and
the live index before publication. The shared `twatch-driver-publication` lock
serializes these publishers; it does not authorize a merge or a release.

## Stage 1: existing native bridge only

Follow the native-only section of `SDR_TEST_PUBLICATION.md`, after the appropriate
default-branch integration and publication approval. The exact original index is
`dbed8d887be0e4d8a4f29fc97487d457dde94783`; any changed predecessor fails closed.
Do not select its `cohort` action for this midpoint.

```sh
python scripts/publish_sdr_test.py preflight --stage native \
  --expected-index-commit dbed8d887be0e4d8a4f29fc97487d457dde94783
gh workflow run sdr-test-publication.yml --ref main \
  -f action=publish -f stage=native \
  -f expected_index_commit=dbed8d887be0e4d8a4f29fc97487d457dde94783
```

Only 1.0.3 is published. Have the operator install it with Firmware Update,
restart, and report actual Runtime 0.1.34, healthy Clock and retained data. Stop
if unhealthy. Host `boot-healthy` simulations do not satisfy this requirement.

## Stage 2: separate midpoint confirmation and dispatch

After the actual report, get the exact live stage-1 index commit and display the
required statement. It binds midpoint source, native bridge, final OTA digest,
acceptance digest and stage-1 index commit:

```sh
git ls-remote origin refs/heads/release-index
python scripts/publish_midpoint_test.py confirmation \
  --expected-index-commit STAGE1_INDEX_SHA
```

Ask the operator to confirm that exact statement. Do not automatically pipe its
output into another command or infer physical health from CI. Copy the confirmed
statement into `CONFIRMATION`. Use the actual default branch if not `main`.

```sh
CONFIRMATION='EXACT OPERATOR-CONFIRMED STATEMENT'
gh workflow run midpoint-test-publication.yml --ref main \
  -f action=preflight -f expected_index_commit=STAGE1_INDEX_SHA \
  -f operator_confirmation="$CONFIRMATION"
# Only after the read-only preflight succeeds and publication is authorized:
gh workflow run midpoint-test-publication.yml --ref main \
  -f action=publish -f expected_index_commit=STAGE1_INDEX_SHA \
  -f operator_confirmation="$CONFIRMATION"
```

The workflow rechecks original ZIP custody, exact derivation, both evidence modes,
real catalog parsing, current default source, published bridge bytes and exact
predecessor. It publishes only an immutable `firmware-v1.0.6` prerelease with
`make_latest=false`, verifies uploaded bytes, then advances only the firmware row
using a non-force push. Every unrelated catalog row remains unchanged.

A release and an index push are not atomic. A late index race can leave verified
assets published without catalog advancement. Report that partial outcome; never
silently rebase or change the expected predecessor. A retry is safe only against
the same unchanged predecessor and exact accepted bytes. An already advanced
index is a terminal result to inspect, not permission to rewrite the same version.

## Local verification and initial freeze

For offline verification, put the original, unrepacked ZIPs at `bridge.zip`,
`ordinary.zip` and `native.zip` in a local input directory:

```sh
python scripts/publish_midpoint_test.py verify --artifact-dir /inputs/original-zips
python -m unittest discover -s tests -p test_midpoint_publication.py -v
```

The initial `freeze` operation refuses to replace canonical acceptance/evidence.
It requires explicit hosted input metadata, connector CI snapshots, final build
and normal/sanitized reports, execution custody, independently tested midpoint
bytes and the installed System Apps source checkout. Its `--help` lists those
inputs. No blobs are committed to source. A later candidate needs separately
reviewed identity and tooling; this record is not silently replaced.
