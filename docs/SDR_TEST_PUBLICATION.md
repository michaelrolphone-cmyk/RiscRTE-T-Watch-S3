# Manual two-stage SDR test publication

This workflow is prepared but inactive until a reviewed acceptance file is committed.
It never substitutes the frozen `release/product.json` (Watch 1.0.2), rebuilds accepted
bytes, updates 1.0.2 assets, or advances both stages in one invocation. No device has
been tested or installed by this script. Host evidence is not physical attestation.

The only installed-Watch upgrade route is the existing **Firmware Update** application.
The full 16 MiB images in the immutable releases remain destructive **initial-only**
assets required by the current catalog schema; never send or flash one as an upgrade.
The actual updater selects the nested `ota` URL, preserving NVS and app-data.

## 1. Freeze final successful CI evidence (read-only remote operations)

Wait for the final `T-Watch driver contracts` run, including the normal/sanitized
upgrade proofs and final 18-entry launcher proof, to finish successfully. The source
must contain the final launcher fix. Use the exact run attempt and immutable artifact
ID for `twatch-sdr-upgrade-<40-character-source-SHA>`, not “latest”, an earlier provisional
bundle, or files rebuilt after CI. With `gh` authenticated in this repository:

```sh
python scripts/publish_sdr_test.py freeze \
  --source-sha FINAL_WATCH_SOURCE_SHA \
  --run-id ACCEPTED_RUN_ID --run-attempt ACCEPTED_ATTEMPT \
  --artifact-id ACCEPTED_ARTIFACT_ID
python scripts/publish_sdr_test.py verify
```

`freeze` writes `release/sdr-test-acceptance.json` locally, refusing replacement.
It verifies the successful CI attempt, artifact name/source/timestamps/digest, downloads
and hashes its ZIP, freezes the original 1.0.2 index at
`dbed8d887be0e4d8a4f29fc97487d457dde94783`, and validates both complete payloads,
proofs and catalogs. Review and commit this acceptance record in a branch/PR. Publishing
requires that reviewed record and this workflow on the current default branch, with
the accepted source as an ancestor. A branch push, PR, successful CI, or merge does
not trigger this SDR publication workflow. Merge authorization is separate.

An offline artifact check is also available:

```sh
python scripts/publish_sdr_test.py verify --artifact exact-accepted-ci.zip
```

The ZIP must retain the original GitHub artifact bytes (including its original hash).
Repacking a downloaded directory creates a different artifact and is rejected.

## 2. Publish only native bridge 1.0.3 after explicit publication approval

Review the current live branch and perform a read-only preflight first:

```sh
git ls-remote origin refs/heads/release-index
python scripts/publish_sdr_test.py preflight --stage native \
  --expected-index-commit dbed8d887be0e4d8a4f29fc97487d457dde94783
gh workflow run sdr-test-publication.yml --ref main \
  -f action=publish -f stage=native \
  -f expected_index_commit=dbed8d887be0e4d8a4f29fc97487d457dde94783
```

Use the actual default branch instead of `main` if it differs. The dispatch publishes
only `firmware-v1.0.3` as a prerelease (`make_latest=false`), verifies every uploaded
asset, then performs the existing non-force index push against the exact predecessor.
All app/driver/service rows remain unchanged. It does not create/publish 1.0.4 yet.
A concurrent index change fails closed; do not bypass it or edit the expected index
merely to make a failed command pass. A failure after assets but before the index can
be safely retried against the same unchanged predecessor and accepted bytes.

On the installed Watch, use **Firmware Update** to install the native bridge and
restart. Verify Runtime 0.1.34, a healthy Clock, retained applications/settings/data,
and successful restart. The cloned store intentionally retains its 1.0.2 cohort
identity. Stop if anything is unhealthy. Do not advance the catalog based on CI alone.

## 3. Publish cohort 1.0.4 only after the operator reports a healthy bridge

This is a separate decision and a separate manual dispatch. The script cannot observe
or attest the device. Record the operator's actual confirmation; never fabricate it.
Get the exact stage-1 index commit, then display the required acknowledgement text:

```sh
git ls-remote origin refs/heads/release-index
python scripts/publish_sdr_test.py confirmation --expected-index-commit STAGE1_INDEX_SHA
```

After the operator explicitly confirms that statement, copy its exact text into
`CONFIRMATION`. It is bound to the accepted artifact SHA256 and stage-1 index commit.
Do not automatically pipe the command's output into a publication command.

```sh
CONFIRMATION='EXACT OPERATOR-CONFIRMED STATEMENT'
python scripts/publish_sdr_test.py preflight --stage cohort \
  --expected-index-commit STAGE1_INDEX_SHA --operator-confirmation "$CONFIRMATION"
gh workflow run sdr-test-publication.yml --ref main \
  -f action=publish -f stage=cohort \
  -f expected_index_commit=STAGE1_INDEX_SHA \
  -f operator_confirmation="$CONFIRMATION"
```

The publisher requires the exact frozen 1.0.3 index, verifies its already-published
bridge release bytes, publishes only the accepted 1.0.4 prerelease, and then advances
the index monotonically. Missing/wrong confirmation, a different artifact, skipped
stage, unrelated index changes, or a same-version rewrite all fail closed.

Use **Firmware Update** again to install the native+bootfs cohort. Restart and verify
Clock health before opening Waterfall. This payload excludes NVS, app-data, partition
table, bootloader and empty initial data images. Each stage retains its preceding
complete native/store pair for rollback. Physical OTA/power-loss, RF sensitivity,
power consumption and hardware qualification remain separate unrun checks.

## Verify the tooling

```sh
python -m unittest discover -s tests -p test_sdr_publication.py -v
python -m unittest discover -s tests -p 'test_watch*product.py' -v
```

No accepted CI IDs or hashes are invented in this change. An expired artifact or
unsuccessful/incomplete CI attempt is a blocker; it is never replaced by a fresh local
build under the same acceptance identity. The original product publisher and SDR
publisher share the existing publication concurrency lock and immutable upload/index
routines. Only a manual `workflow_dispatch` on the current default branch may mutate
SDR releases or the live catalog.
