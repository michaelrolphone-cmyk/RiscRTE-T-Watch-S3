# Shared Watch 1.1.22 factory composition

`seal_shared_watch_factory.py` composes the approved expanded ABI3 factory
layout offline. It does not build, flash, publish, migrate an existing device,
or qualify physical hardware/RF behavior.

**FULL FACTORY BIN at 0x0 ERASES CURRENT SETTINGS, NVS and app-data. No automatic
flashing; not an OTA migration.** App-data capacity is still 512 KiB; its
contents are reset to the previously verified empty disk2.1 image.

## Inputs and gates

- Exact clean product and Runtime checkout SHAs, including no untracked source
  inputs. Commit all recipe/profile changes before sealing. Use the selected
  Runtime's newly built `.pio/build/watch-expanded` binaries, never old native
  images with relabeled metadata.
- The complete `staging.json` and `UNSEALED-STORE` inventory: 119 files, 58 ELFs,
  25 apps and 34 providers. The whole inventory must match the source-frozen
  qualified inventory SHA-256, so consistently rehashing altered inputs also
  fails. No missing, extra, changed or symlinked files.
- Runtime 0.2.23, exclusive expanded target/ABI3 identity in both ELF and BIN,
  ELF32 Xtensa and ESP image integrity, embedded input-ELF digest, reviewed
  bootloader hash, exact expanded native partition table, native post-link and
  radio IQ proofs, and source-bound composition limits (64 apps, 40 providers,
  24 policy rows and 24 requirements).
- Original 1.1.21-r1 full BIN SHA-256
  `4e43fc376021779a2d7a5cada96aee255735d5db1eb0e896c5aacf65bb3889bc`.
  Only its `0x270000:0x2f0000` app-data slice is used, with SHA-256
  `5f03c248f2de31c4da9ae8d9bc2033df064cee5e37694a9982f70fbb2f1d2ef0`.
- The original formatting witness defaults to
  `docs/watch-recovery/appdata-image.json`. It is verified by the selected
  Runtime helper and copied unchanged, including its historical ABI2 layout
  label. The factory record binds its hash and explicitly records that label;
  it is a formatting witness for unchanged app-data geometry, not an ABI3
  whole-image manifest.

Use Python with the repository requirements, pyelftools and the pinned build's
esptool import available. If esptool is provided by PlatformIO rather than the
Python environment, add its `packages/tool-esptoolpy` directory and bundled
`packages/tool-esptoolpy/_contrib` dependency directory to `PYTHONPATH`.

## Reproducible sequence

Set `PRODUCT_SHA`, `RUNTIME_SHA`, `STAGING`, `RUNTIME`, `OUT` and `BASELINE` to
verified local inputs. `OUT` must be outside the tracked source trees or under
an ignored artifact directory. Each output path must be new.

```sh
common=(--staging "$STAGING" --runtime "$RUNTIME" \
        --runtime-sha "$RUNTIME_SHA" --product-sha "$PRODUCT_SHA")
python scripts/seal_shared_watch_factory.py seal-store "${common[@]}" \
  --output "$OUT/sealed"
python scripts/seal_shared_watch_factory.py admission "${common[@]}" \
  --sealed "$OUT/sealed" --mode normal --output "$OUT/normal.json"
python scripts/seal_shared_watch_factory.py admission "${common[@]}" \
  --sealed "$OUT/sealed" --mode asan-ubsan --output "$OUT/sanitized.json"
python scripts/seal_shared_watch_factory.py factory "${common[@]}" \
  --sealed "$OUT/sealed" --normal-receipt "$OUT/normal.json" \
  --sanitized-receipt "$OUT/sanitized.json" --baseline-bin "$BASELINE" \
  --output "$OUT/factory"
```

Sealing replaces only `cohort.json`, binding 1.1.22/0.2.23 to the exact product
source SHA and native bytes. The pinned SPIFFS builder uses `0x550000` bytes,
checks all files with an independent reader and requires two free blocks.
Every subsequent command reproduces and compares those bytes and proof records.

Admission compiles the actual Runtime host harness and self-validates all 58
app/provider ELFs against the selected native ELF without target instructions
or native I/O. Normal and ASan/UBSan runs are separate; leak detection is
explicitly disabled because it is unsupported under some executor ptrace
setups. This does not disable address or undefined-behavior sanitization.
Receipts bind source revisions, seal/store/native hashes, counts and composition.
A missing, failed, stale, differently instrumented or incomplete receipt blocks
factory output. Receipts are local execution evidence, not signed attestations.

Factory output contains one 16 MiB full BIN, `factory.json`, unchanged
`appdata-image.json` and `SHA256SUMS`. The record includes all eight partitions,
component and partition hashes, free blocks, erased inactive bank, erase warning
and explicit lack of hardware qualification. Separate native/store components
are not duplicated into the factory output; the sealed store is retained for
admission/reproduction evidence. No OTA package is emitted.

## Focused tests

```sh
python -m unittest discover -s tests -p test_seal_shared_watch_factory.py -v
# Optional real input inventory, never needed by source CI:
WATCH_SHARED_STAGING="$STAGING" python -m unittest discover -s tests \
  -p test_seal_shared_watch_factory.py -v
```
