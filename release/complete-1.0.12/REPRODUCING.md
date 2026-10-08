# Reconstructing the accepted Watch 1.0.12 sources

The release publishes the accepted full image unchanged, SHA-256
`af958e480a3183bde3f448e97930d56b9aeea567a664428892b917a878d014ff`.
It is a 16 MiB initial image at offset 0x0 and erases saved data.
The separate paired file remains separate and has no published updater route.

## Original identities and publicly available sources

`source-custody.zip` contains five incremental Git bundles, their public
prerequisites, original commit IDs, public tree-equivalent commits and tree
hashes in `source-equivalence.json`. Original Watch source is
`f3f8755619e94d0078ef16d43d9c6039bee46b8d`; original Runtime 0.1.55 source is
`2abc312217fadb04ac0d9c994ecb38edc15edf6a`. The equivalent public Watch commit is
`c2b340a6bce466a24dea8eea5d09213e7f2298d9`; Runtime's equivalent production tree
is `ad956b518e99fa380419892a87e6367e3980dcd0`. Runtime 0.1.60 is excluded.
The original identities are restored, rather than replacing the build pins
with later main-branch commits. This preserves compiled source markers.

`reconstruction-inputs.zip` supplies the immutable historical authoring inputs
which the original builder checks: RF 1.0.8 app evidence and the exact accepted
1.0.11 initial-origin files. These are build inputs, not additional published
update routes. Every input is hash checked before use. Generic Drivers is
pinned to `4088b6892c2e2654b0342f04a7d191068e4a8e2e`.

Git stores this ZIP as two transport files, `reconstruction-inputs.zip.gz.part1`
and `reconstruction-inputs.zip.gz.part2`, to fit the repository upload limit.
The helper bounds both part reads and gzip expansion, verifies the joined gzip,
and restores the original 13,171,498-byte ZIP with SHA-256
`a65b56c15461807c197c7dbbc8b0eb585a9d1a242f5063f96f011c6829670be3`.
The published `reconstruction-inputs.zip` name and contents are unchanged.
When reconstructing directly from a repository checkout, hydrate with:

```sh
python scripts/reconstruct_watch_112_sources.py hydrate \
  --source-custody release/complete-1.0.12/source-custody.zip \
  --build-inputs-gzip-parts \
    release/complete-1.0.12/reconstruction-inputs.zip.gz.part1 \
    release/complete-1.0.12/reconstruction-inputs.zip.gz.part2 \
  --output "$PWD/reconstructed"
```

The published release assets use the original ZIP and the following commands.

## Clean remote reconstruction

On Linux x86-64 with Python 3.11, Git, a host C/C++ compiler and network access
to GitHub and the official PlatformIO registries, place these release assets
in one directory:

- `source-custody.zip`
- `reconstruction-inputs.zip`
- `reconstruct_watch_112_sources.py`

Run from that directory:

```sh
python3 reconstruct_watch_112_sources.py hydrate --output "$PWD/reconstructed"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r reconstructed/RiscRTE/requirements-ci.txt
python -m pip install -r reconstructed/RiscRTE-T-Watch-S3/scripts/requirements.txt
python reconstruct_watch_112_sources.py build --output "$PWD/reconstructed"
```

The hydrate action verifies each bundle against its public prerequisite,
restores all five original source commits and checks their recorded tree
hashes. It also fetches the pinned Drivers and LittleFS dependencies. It
refuses to overwrite an existing directory. If interrupted, use a new output
directory after inspecting the failure.

The build action compiles the original Runtime `esp32s3-16mb-appdata-iq` target,
creates the verified empty LittleFS image, stages the Runtime input, compiles
all 22 Watch apps and the current provider sources with Xtensa GCC 8.4.0,
and assembles a fresh initial image through the original candidate builder.
PlatformIO and target package versions are pinned in the original Runtime
source. The compiler defaults to PlatformIO's installed toolchain; pass
`--cc /absolute/path/to/xtensa-esp32s3-elf-gcc` when necessary.

A clean reconstruction from the bundled original commits reproduced the exact
accepted full-image SHA above. `reconstruction-proof.json` records that result.
The hosted release workflow repeats this compilation and requires the same full
image hash before publication.

Fresh output is under
`reconstructed/RiscRTE-T-Watch-S3/dist/reconstructed-1.0.12-initial/`.
`reconstructed/reconstruction-result.json` records the newly built image
hash and whether it matches the accepted image byte for byte. A mismatch
stops the helper after writing the report. It never relabels or overwrites the
release. Debug paths, tool versions, or dependency changes can affect outputs;
inspect fresh proof if the comparison fails. The original full build and host proof files remain in
`source-custody.zip` unchanged.

This initial-image reconstruction does not repeat the preserving-update
transaction suite or establish physical sleep, RF, or power measurements.
The release preserves those historical host proofs and the owner's later
acceptance of the delivered integrated build without expanding either claim.
