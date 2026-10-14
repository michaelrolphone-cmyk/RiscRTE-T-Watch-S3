# T023 automatic core bridge: source-only composition

## Status and inputs

The opt-in composition is source-tested; no new product binary, public feed,
release, device execution, or complete native/store admission is claimed here.
The combined Runtime and System source pins remain **pending tested commits**.
Historical checkpoint/admission JSON and `t023-migration-policy.h` describe their
original exact sources; they do not qualify a newly composed bridge automatically.

Minimum reproducible inputs:

1. The complete verified T-Watch 1.1.33, cohort source 96af8531017df79e543dc064a728ef1f1d1577aa baseline store,
   including every manifest, ELF, data file, board/boot/cohort policy and metadata.
2. Exact newly built Home (`default.elf`, `default.json`) and Springboard
   (`springboard.elf`, `springboard.json`) directories. Product declarations for
   both apps are retained. Existing grants/private namespaces are preserved.
3. System installed-apps output built from the tested combined System/Runtime
   checkpoints with all of `--native-feed --boot-profiles --internal-packages`,
   `--feed-product twatch-s3`, and an explicit verified product feed URL.
   `build.json` must describe those flags/product and the exact `driver.elf` hash.
   The request ABI is System's `lib/PortableApps/include/RiscProvisionRequestV1.h`.
4. System `scripts/build_internal_packages.py` output (`driver.elf`,
   `manifest.json`), built against the same exact Runtime SDK.
5. Native `firmware.bin` from the exact product profile and selected source-bound
   overlays; a candidate product version and a full 40-character source revision.
   An explicit `--runtime-version` is required in bridge mode and must match the
   firmware binary's `RISC_RUNTIME_VERSION:` marker. The combined native version
   for this candidate is `0.2.24`; the baseline version must not be inherited.
6. A JSON list of exact native-selected provider manifest paths. Supply `[]`
   explicitly if the selected native policy has no provider images. This list
   must match the native build, not a guessed list of hardware providers.

Build service inputs with System's existing builders, for example:

```sh
python "$SYSTEM/scripts/build_installed_apps.py" \
  --runtime-repo "$RUNTIME" --output-dir "$CATALOG" \
  --internal-packages --native-feed --boot-profiles \
  --feed-product twatch-s3 --feed-url "$VERIFIED_PRODUCT_FEED_URL"
python "$SYSTEM/scripts/build_internal_packages.py" \
  --runtime-repo "$RUNTIME" --output-dir "$INTERNAL"
```

Stage the product's native config/header in the matching Runtime checkout and
select `env:watch-t023-boot-profiles` with PlatformIO. It inherits the existing
T023 profile and only adds `RISC_NATIVE_PROVISION_REQUEST=1`. The legacy
`env:watch-t023` remains available without that flag. Runtime must include the
request queue, complete 160-file inventory, and boot/default app internal fallback
changes. Do not substitute a different product's native profile or partitions.

```sh
python scripts/compose_provisioning.py \
  --baseline "$BASELINE_STORE" --home "$HOME_BUILD" \
  --springboard "$SPRINGBOARD_BUILD" --catalog "$CATALOG" \
  --internal "$INTERNAL" --firmware "$FIRMWARE_BIN" \
  --version "$CANDIDATE_VERSION" --source-revision "$PRODUCT_SOURCE_SHA" \
  --runtime-version "0.2.24" \
  --output "$NEW_STORE" --boot-profiles \
  --native-provider-manifests "$NATIVE_MANIFEST_LIST_JSON" \
  --composition-report "$EVIDENCE_DIR/composition.json"
```

`NEW_STORE` must not exist. The report must be outside the store. The composer
preserves the full file inventory, hashes every file, verifies unchanged bytes
outside the six intentional boot/cohort/Home/Springboard replacements, and
rejects stores exceeding 160 files. This limit does not establish SPIFFS fit;
pack the entire final store and perform exact native/store admission separately.

## Image policy

The product remains internal-only: volume0, internal_volume0, no fabricated
SD provider, no removable storage grant, and no image_source additions. The
composition rejects a removable image source or external volume rather than
silently erasing that policy. The public core profile must emit `mirrors: []`.
The 1.1.33 inventory has 121 files and all boot-owned app ELFs available internally;
this source fixture is not a newly built or admitted T023 candidate.

## Optional lossless provider compaction

Default composition copies both new provider ELFs byte-for-byte. If the packed
store is too tight, explicitly add these arguments to the bridge command:

```sh
  --compact-new-providers \
  --compiler "$XTENSA_TOOLCHAIN/bin/xtensa-esp32s3-elf-gcc" \
  --debug-sidecar-dir "$EVIDENCE_DIR/original-provider-elfs" \
  --composition-report "$EVIDENCE_DIR/composition.json"
```

Only newly added `installed-apps/driver.elf` and `pkg-internal/driver.elf` are
eligible. No baseline app, driver, data file or manifest is compacted or removed.
The original catalog build receipt is validated before copying; the checked
compaction runs before the final image_source digests and inventory are computed.
The caller must provide the actual compiler path and matching adjacent objcopy.
Python must have pyelftools available for this explicit mode.

This uses the product's existing `scripts/compact_current_elf.py` unchanged. Its checks
compare all retained header/segment, section-order, loaded-section, global/weak
symbol, referenced-local-symbol and relocation semantics. The composition report
retains the complete compactor receipt plus every retained semantic field (raw
section/segment bytes represented by length and SHA-256), component equality
results, before/after semantic hashes, checker-source hash and tool details.

The full original ELFs remain under the separate debug-sidecar directory, using
the same two relative paths. Existing sidecars are never overwritten. Input trees,
store paths, sidecar/report aliases and nested escaping symlinks are rejected
before composition. The two source build outputs remain unchanged. Actual final
store packing and complete native/store admission still decide whether this fits;
compaction does not change partitions or claim admission by itself.

## Qualification before use

Regenerate and qualify any exact native migration policy against the actual
source/target snapshots. The historical embedded policy cannot authorize new
source revisions or changed app policy JSON. Old native firmware cannot be
assumed to accept the bridge directly; use only a separately qualified preserving
native-first path. Do not reset saved data, repartition, format, or claim direct
OTA migration without evidence.

Run `python scripts/test_t023_boot_profiles.py`. These tests use explicitly
synthetic source fixtures to check complete 160-file preservation, unchanged
manifests/data, grants/namespaces, content addressing, default-app fallback,
transitive storage/native closure, cycle rejection, opt-in behavior, rejected
mismatched catalog receipts, missing images, and internal-only operation.
They are not substitutes for real ELF/native admission or hardware checks.
