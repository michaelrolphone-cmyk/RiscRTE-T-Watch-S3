# Watch 1.0.18 software checkpoint

This separate cohort selects shared app cleanup ordering and the exact-source
firmware updater. All 23 apps remain. The 21 apps using the common adapter have
new deployment versions; Clock/default and the other 22 provider artifacts are
byte-identical to the frozen Watch 1.0.17 binding. Board policy, grants, storage
ownership and the native Runtime 0.1.73 image are unchanged.

The common adapter pauses background services before app-owned cleanup can
refuse or retain its invocation. Clean exits still allow later apps to resume
enabled broadcasting. Firmware provider 0.1.5 selects exact installed-source
routes, including the active-store digest, and checks that identity again before
staging. Existing single-record catalogs retain their old behavior. No catalog
or release is deployed by this checkpoint.

## Frozen bytes and source identities

- App build: `65d6307f7c89193402f9bdf60dbbd15d436e1457`
- Hardened equivalent app builder: `96aa4452a1e4ff2a636de14e7affeb842e9687a9`
- Original package recipe: `014f3e7e4566d4e87f0ab4a1c9e538e557224faa`
- Native source: `b587df55298e0bb8e676b3d59ca13679c0267bf7`
- Initial 16 MiB image SHA256:
  `216ed021bb42eca460b5ef1fd0c41b5e4a7a39a6230dafded4819530d7eafafb`
- Paired payload, 6,577,888 bytes, SHA256:
  `f5949967d28e91cc58e83913dbbe1744f0a291bec3604e46acdaa1a3cd29e7be`

The full initial image erases user data. The paired payload is firmware followed
by bootfs and is **not a serial flash image**. These hashes identify privately
saved test artifacts, not published release downloads. No device operation or
hardware acceptance is claimed.

The hardened builder reproduces all 21 app ELFs and the updater ELF exactly.
Its new cohort source revision is the only changed store member, so its complete
image is a distinct artifact. The original image and its proofs have not been
replaced or relabeled. A fresh build at a new public commit similarly receives
new source provenance; it must not be presented as the original tested image.

## Restore exact Watch history

`watch-sources.bundle` contains only Watch source history and requires the
existing public commit `a0f2894bb3513d024653e71ce7e52733804e19e8`.
`source-custody.json` records its digest and six original source refs. From a
checkout containing that prerequisite:

```sh
git bundle verify docs/lifecycle/watch-1.0.18/watch-sources.bundle
git fetch docs/lifecycle/watch-1.0.18/watch-sources.bundle \
  'refs/watch-custody/1.0.18/*:refs/watch-custody/1.0.18/*'
git worktree add --detach ../watch18-original \
  refs/watch-custody/1.0.18/app-build
git worktree add --detach ../watch18-hardened \
  refs/watch-custody/1.0.18/hardened-build
```

Use `scripts/build_lifecycle_routes.py --help` for the explicit build inputs and
`scripts/package_lifecycle_routes.py --help` for the exact package inputs. The
configuration keeps the app SDK/source Runtime 0.1.55 pin distinct from the
native Runtime 0.1.73 pin. The frozen 1.0.17 binding, native candidate, source
checkouts and GCC 8.4.0 toolchain are independently verified inputs.

This bundle does not contain dependency repositories or provisioning payloads.
The separately pinned System model-client header is still pending publication;
a remote-only full app rebuild remains dependent on that publication. The
independent initial-provisioning payload publication also remains separate.
Neither pending payload has been copied into this source checkpoint.

## Qualification status

Recorded software checks pass: all 46 target ELFs admit under the selected
native; 36 actual Runtime/Clock/Contexts lifecycle and model-import cases pass
normally and with ASan/UBSan; the updater has 72 source-route cases; common
cleanup, alarms, quick controls, low battery and radio regressions pass.
Independent review verified the exact package, all 227 compiler inputs and
feature flags. The 95-file store leaves 10 complete SPIFFS blocks free, above
the required four-block reserve.

The hardened builder additionally passes 10 source-custody regressions and six
full-verifier mutation cases. Package verification rejects 13 coherent byte,
provenance, claim, inventory and notice changes. Historical Watch 1.0.17
preserving receipts remain unchanged. Exact-source preserving matrices for this
new target are still in progress; see the separate preserving-test ref and its
result receipts before claiming those routes qualified. Flash, network, target
instructions and physical power behavior remain outside the host proofs.

Demand-retained activation is a separate exploratory policy qualification. This
cohort continues to select `provider_activation: demand`.
