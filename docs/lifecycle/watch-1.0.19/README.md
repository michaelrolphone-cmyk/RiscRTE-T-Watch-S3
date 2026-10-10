# Watch 1.0.19 demand-retained policy

This cohort changes only `boot.json` activation policy and `cohort.json`
identity. All 23 app ELFs/manifests, all provider bytes, board/grant policy,
licenses and the selected Runtime 0.1.73 native remain identical to Watch 1.0.18.
The 95-file SPIFFS store still has 10 complete free blocks.

The foreground Clock's existing promotion call now retains currently active
providers and arms later retention without loading unused providers. First
authorized use loads a deferred provider; its mapping then survives ordinary
app/default handoffs. Failure and retained-cleanup fences stay active.

## Exact sources and saved artifacts

- Policy/package source: `39fe8cbfc6d8f4e9db51ec06c5f64e83c849042c`
- App build source: `65d6307f7c89193402f9bdf60dbbd15d436e1457`
- Native source: `b587df55298e0bb8e676b3d59ca13679c0267bf7`
- Initial image SHA256:
  `1838520f1e13eea16ead49720417c002b494e9be3fe663db2090483489aff2e6`
- Paired payload SHA256:
  `b92f4e593363f7f5b8f37bccbdb13fdaa4c801b3b6a6d982c8bf13106864b3bf`

The initial image erases user data. The paired payload is not a serial flash
image. These identify internally saved test artifacts, not a published release
or live update feed. Original Watch 1.0.18 artifacts remain unchanged.

The package builder independently verifies the exact frozen Watch 1.0.18 input,
reconstructs the two allowed metadata changes, repacks and independently reads
SPIFFS, validates the exact native candidate, and compares every final member.
It does not trust source or qualification claims supplied by the output receipt.

## Qualification and limits

All 60 exact-artifact execution cases pass normally and with ASan/UBSan: Clock
startup and context-loss fences, enabled Contexts, owner model import, late use
of all seven previously deferred providers, repeated app/default handoffs,
clean retries and retained failures. These cases execute the actual Watch 1.0.19
store metadata without JSON substitutions. Sixteen package mutation cases pass.
Leak detection is disabled because the host executor cannot run LeakSanitizer.

The earlier controlled startup comparison measured 26 versus 19 module-load
calls. The avoided first mappings and reloads total 1,548,952 target load-segment
bytes. This is static composition evidence, not a hardware free-heap saving.
The complete 24-provider retained set totals 2,133,464 load-segment bytes before
the active app. Contexts alone has 327,752 bytes of BSS; the smaller state-size
assertion excludes temporal/inference state. Native allocations, transient
loader work and allocator fragmentation are not measured by those totals.

Exact-source preserving matrices and their receipts are separate from packaging
and are still in progress. Installed Runtime 0.1.55 rejects `demand-retained`
before I/O, so older Watch versions require the qualified native bridge first.
The focused exported Watch 1.0.18 bank1 snapshot matches its completed full
matrix, allowing a real subsequent bank1-to-bank0 policy hop. No hardware,
physical radio/network/flash operation, merge or release is claimed here.

## Restore original qualification source

The bounded Watch-only `watch-sources.bundle` requires public prerequisite
`a0f2894bb3513d024653e71ce7e52733804e19e8`. It contains original policy,
package-test, graph-test, preservation and selected-state-replay commits.
`source-custody.json` records the exact refs and hashes. Restore them with:

```sh
git bundle verify docs/lifecycle/watch-1.0.19/watch-sources.bundle
git fetch docs/lifecycle/watch-1.0.19/watch-sources.bundle \
  'refs/watch-custody/1.0.19/*:refs/watch-custody/1.0.19/*'
git worktree add --detach ../watch19-original \
  refs/watch-custody/1.0.19/package
git worktree add --detach ../watch19-graph-tests \
  refs/watch-custody/1.0.19/artifact-graph-tests
```

Use the restored scripts' `--help` for explicit verified inputs. The new graph
runner's `--policy-package`, `--policy-repository`, `--policy-source` and
`--parent-package` select the actual artifact. `--activation-probe` remains a
separate experimental path and cannot qualify a deployable artifact.

No dependency repositories or separate provisioning payloads are included.
Remote-only app rebuilding still depends on the separately pending System
model-client header publication described in the Watch 1.0.18 checkpoint.
