# T-Watch 1.1.40 native IDF 6.1 exact-byte release transport

The native candidate was produced and software-qualified by official Runtime CI
[run 38797200408, attempt 1](https://github.com/michaelrolphone-cmyk/RiscRTE/actions/runs/38797200408),
with all four matrix jobs passing at Runtime source
`659d859acb122640ef4003bb8d7099501d4381be`.
The original compiled product source is `74f7491dc470b92dfa41fce41bf0c500f3714a94`.
The later transport publication commit/tag is recorded separately in `release.json`.

## Limits

- This is a prerelease, software-qualified and hardware-pending.
- The factory image erases internal saved settings and data.
- No data-preserving SDK migration or OTA kit is supplied. Separate firmware,
  bootloader, partition and store files are evidence, not a flashing procedure.
- Exact deployed-bootloader boot, health confirmation and rollback remain untested.
- Released application/provider payloads, board/boot composition and settings/data
  layouts are retained as checked by the original candidate qualification.
- No physical device was accessed during these builds or checks.

## Immutable custody

`docs/native-idf61/release-transport.json` pins the exact original CI artifact,
all source revisions, candidate outputs, qualification, and Runtime release
manifest. The manifest SHA256 is
`ddf5e3be350658b53bffa023fd3fbc9771c11fce25065f9bf6021ab5ca015d29`.
The public [Runtime0.4.0 release](https://github.com/michaelrolphone-cmyk/RiscRTE/releases/tag/firmware-v0.4.0)
retains the original CI ZIP without unpacking or repacking it.

The offline `scripts/transport_native_idf61_release.py` verifies every ZIP member,
archived workflow/run identity, clean source-before/after records, source lock,
same-process single-job build closure, locked native artifacts, complete normal
and sanitized ELF admission, and hardware limits. It copies the candidate bytes
and original evidence ZIP unchanged. Source-bound `release.json` and complete
`SHA256SUMS` describe all 13 release assets.

The repository-owned workflow runs only on `work/native-idf-6.1` when the exact
contract path changes. Transport requires a finalized contract; the separate
publication job additionally requires `publication_enabled=true`, the exact
repository and branch, and previously absent release/tag names. A create-only
Git refs request atomically creates the exact source tag before release creation
with `--verify-tag`. A failed publication can leave that new tag for explicit
review, but never moves or replaces an existing tag. All public assets are
redownloaded and hash-verified. Historical release workflows are unchanged.

## Local checks

`python tests/test_native_idf61_release_transport.py` runs 21 positive and negative
cases: unsafe ZIP paths/types/duplicates, disabled contracts, wrong run/hash or
inventory, changed native input/payload, dirty source, detached/parallel-build
claims, hardware claims, incomplete ELF admission and exact tag creation.
No compiler or hardware access is needed for this transport.

To reproduce only the verified copy operation, supply the exact public inputs:

```sh
python3 scripts/transport_native_idf61_release.py \
  --contract docs/native-idf61/release-transport.json \
  --runtime-manifest inputs/Runtime-0.4.0-release-manifest.json \
  --evidence inputs/Runtime-0.4.0-Watch-1.1.40-Native-IDF61-Evidence.zip \
  --source-revision FULL_TRANSPORT_COMMIT --output NEW_OUTPUT_DIRECTORY
```
