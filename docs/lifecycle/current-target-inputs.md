# Historical lifecycle custody and current source successors

`watch-1.0.18/source-custody.json` and `watch-1.0.18/watch-sources.bundle`
remain original evidence. Their target-input hashes describe the restored
Watch 1.0.18 `app-build` commit, not every later working tree.

The previous snapshot check compared those historical hashes directly to the
current tree. On mounted Files product source
`628f72b09786880edeafa7c161aedd7114c2d7bc`, it fails on
`apps/clock/watch_motion_client.h`. Both that header and the checker are
byte-identical to delivered Watch 1.1.15 source
`afdab33b66d18d2afc5d9da3abdbcfe90490941a`. The header's current diagnostics and
persistent tap-setting behavior predate the mounted Files composition. The
other 13 historical target inputs still match their original hashes.

`current-target-inputs.json` separately selects the one evolved live input
from that delivered source commit and records its SHA256. The checker:

1. Verifies the original bundle, all recorded commits/trees and selected code.
2. Verifies all 14 original target hashes against the restored original tree.
3. Requires every live target to remain byte-identical to that original input,
   unless it has an explicit successor entry.
4. Requires a successor's full immutable source commit to be an ancestor of
   the checked-out source, verifies the pinned blob's hash, and requires the
   live bytes to match it exactly. Missing/linked files, scope expansion,
   redundant successor entries and mutable source refs are refused.

Do not rehash or replace an original receipt to admit a successor. A later
intentional change to a selected live input requires a separate reviewed
successor entry. The existing compiler dependency and qualified-source
admission checks remain unchanged. This snapshot check does not establish a
new target build or hardware qualification.

## Regression commands

```sh
python scripts/check_lifecycle_source_snapshot.py
python -m unittest discover -s tests -p 'test_lifecycle_source_*.py' -v
python tests/test_mounted_files_recipe.py
```

The snapshot regressions use real temporary Git repositories and bundles.
They cover original and evolved inputs, inherited successors across unrelated
product changes, rejected historical/live rehashes, omitted/extra successors,
mutable/nonancestor pins, attempted rollback of a selected successor,
changed original code, altered bundle/tree evidence and missing/linked inputs.
The historical compiler-input regression file is preserved byte-for-byte.
