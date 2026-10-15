# Source-closed native SDK 6.1 candidate packaging

This is a new, offline candidate path. Historical launch-brightness/native-faces
recipes, release pins and preservation assertions are unchanged. They intentionally
require the old native firmware byte-for-byte and cannot package this migration.
No command here reserves versions, publishes, updates catalogs, accesses serial
ports, flashes hardware or creates a user-ready preserving-update kit.

## Released payload contract

`released-baseline.json` is decoded from the exact published full factory image,
not reconstructed from current source defaults. It includes every store member's
size/hash, every ELF's undefined imports (both symbol tables), partition and
bootloader region hashes, native binding and descriptor/OTA identity.

- Watch 1.1.39: product `2c00363b6371276df087f71bea5b9a89a1d20e44`, 121 files, 59 ELFs.
- Wave 0.1.48: product `3fe09c68019cd8d258789eb903d55c6b9bfbbe10`, 128 files, 62 ELFs.
- Both source native Runtime `4107eaeedd8c801eeaf7deb1c7bc4a943cd27342`.
- Both use expanded paired store ABI 3, 0x550000-byte boot stores, native slots
  0x10000/0x840000 of 0x260000 bytes, and independent appdata 0x270000/0x80000.

The recipe retains all released application/provider bytes, manifests, board,
boot, settings authority, native Home/faces, Springboard and brightness fixes.
Only `cohort.json` changes in the store. In particular it preserves Wave's
selected USB device MSC and USB SD Transfer payloads. It neither selects the
experimental USB host controller nor guesses VBUS wiring.

There are no private OS/CPU ABI 1 imports in either released store. The selected
Wave MSC ELF imports only memcpy/memmove/memset/strcmp. Keeping ordinary ELFs
requires successful production-source admission against the exact candidate's
linked public export tables, including the resident time32 adapter. A native
private import in either ELF symbol table is rejected, including hidden/weak
imports; a sidecar cannot authorize ABI 1 or ABI 2. A future private provider
selection needs a separate product-owned, compiled-policy recipe.

## Immutable inputs

Run with the pinned SDK's Python dependencies and GCC15 toolchain. Each operation
accepts `--source ROLE=CHECKOUT`; the required roles are product, runtime, system,
drivers, sdk and image_helper. The product role is this checkout. `image_helper`
is the explicitly pinned T-Watch source checkout containing the independently
read-back SPIFFS packer and existing production-source admission harness. It may
be the same checkout as product for T-Watch. Wave must pass a separate source
checkout rather than implicitly resolving a moving branch.

`freeze` records exact Git commit and tree IDs, recursive submodule pins,
compiler digest/version, native ELF/BIN/MAP/bootloader/partition hashes,
sdkconfig, compilation database and build descriptors. All source checkouts
must be clean at their immutable pins. No copied firmware artifact snapshot is
needed. The SDK pin is `fff9895c82d744c7237be8847347bdd1b07c6643`; GCC is
`esp-15.2.0_20251204`, version 15.2.0.

The System/Drivers pins describe the migrated toolchain/ABI qualification source
cohort. They do **not** falsely claim to have rebuilt preserved released payloads.
Those bytes retain their released-product provenance and exact recorded hashes.
Current qualified shared source pins are System
`cb4bf2547b89e14a721d4a4bb6ada4f5f4750aed` and Drivers
`03116cd2a6d881fafb28f20490e9af48c9179633`; freeze must use the final explicitly
selected clean commits, never a substituted generic smoke-test ELF.

Example command structure (replace uppercase paths and source choices with the
actual immutable candidate inputs; do not run against an active build):

```sh
python scripts/native_idf61_candidate.py audit-baseline \
  --source product=PRODUCT --source runtime=RUNTIME \
  --source system=SYSTEM --source drivers=DRIVERS \
  --source sdk=SDK --source image_helper=WATCH_HELPERS \
  --baseline RELEASED_FACTORY --output baseline-audit.json

python scripts/native_idf61_candidate.py freeze \
  --source product=PRODUCT --source runtime=RUNTIME \
  --source system=SYSTEM --source drivers=DRIVERS \
  --source sdk=SDK --source image_helper=WATCH_HELPERS \
  --native-build COMPLETED_BUILD --compiler GCC15 \
  --candidate-version SELECTED_VERSION --output source-lock.json

python scripts/native_idf61_candidate.py qualify \
  --source product=PRODUCT --source runtime=RUNTIME \
  --source system=SYSTEM --source drivers=DRIVERS \
  --source sdk=SDK --source image_helper=WATCH_HELPERS \
  --native-build COMPLETED_BUILD --compiler GCC15 \
  --baseline RELEASED_FACTORY --lock source-lock.json --output NEW_DIRECTORY
```

The parent release process chooses SELECTED_VERSION. A local prerelease may be
`MAJOR.MINOR.PATCH-idf61.RUNTIME12`; the suffix must match the selected Runtime.
Passing a version does not reserve, tag or publish it. Every output remains
marked candidate/hardware-pending with `publication_enabled: false`.

## Qualification gates

The candidate must pass all gates before output files are written:

1. Exact released factory, native/store binding, member inventory and unchanged
   board/boot/manifest authority; no private provider imports.
2. Clean immutable Runtime/product/System/Drivers/SDK/helper sources and recursive
   submodules, recorded compiler and artifact hashes, then recheck at completion.
3. Actual native compilation database matches the pinned source roots, native
   compiler family, native-IDF mode and every product profile definition.
4. ESP image integrity and ELF-to-BIN regeneration; exact paired partition bytes,
   bounded slots and 16MiB flash geometry; QIO/80MHz and octal80MHz PSRAM.
5. App descriptor keeps `arduino-lib-builder` solely as installed admission
   compatibility metadata. SDK6.1 identity is real; no Arduino core/component or
   runtime symbols may be linked. No private host-controller policy is selected.
6. Native rollback enabled, no introduced secure boot/encryption/anti-rollback,
   unchanged security version; explicit native startup and rollback operations.
7. Exact final ELF IQ SRAM/IRAM exclusion proof, reserved memory table/ROM aliases,
   internal stream registry, IRAM yield and ordinary-ELF time32 boundary.
8. Production Runtime/CPU/ELF cohort admission for every retained payload in both
   ordinary and ASan/UBSan host runs. Wave retains its exact native settings writer
   profile and source-extracted CO5300 acceptance predicate. Lowest hardware and
   storage boundaries must remain unused.
9. Deterministic SPIFFS packing twice, independent readback, bank digest binding,
   and 496 inactive-bank/selection/corruption fault cases over both active banks
   and both OTA selector sectors. These are software fixtures, not hardware proof.

Outputs include separate new native bootloader/firmware/partitions/store, an
explicitly destructive factory candidate, exact input lock, detailed qualification
and final SHA256SUMS. There is no preservation ZIP or flashing command.

## Bootloader migration boundary

Both published images have descriptor project `arduino-lib-builder`, descriptor
version `esp-idf: v4.4.7 38eeba213a`, secure version 0, and initial OTA sequence 1,
state 2 (VALID), with the other selector erased. Both exact 0x0000–0x8000 bootloader
regions hash to `6ac230d6941c798d91b83334598bb2266a417200aec3b15c74d4d69787e6a269`.
The pinned Arduino 2.0.17 ESP32-S3 sdkconfig enables first-boot rollback. Released
native code defers Arduino confirmation and the paired-bank health path owns
explicit confirmation/rollback. A new SDK6.1 bootloader must retain that behavior.

[Espressif's SDK6.1 ESP32-S3 bootloader contract](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/api-guides/bootloader.html)
supports older bootloaders loading newer-IDF applications and recommends keeping
the old bootloader when downgrade is required. It also requires production OTA
tests to use the exact deployed bootloader. Therefore unchanged partition geometry
alone does not establish migration safety. The destructive factory contains the
new native bootloader; the old-bootloader transition image exists only in memory
for fault modeling, and cannot be emitted as an installable preservation kit.

The SDK6.1 [OTA guide](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/api-reference/system/ota.html)
classifies bootloader/partition replacement as power-loss-vulnerable. This recipe
never writes those regions as part of an inactive-bank preserving update. It also
does not claim that a newer bootloader can safely roll back to old-IDF firmware.

A future preserving migration must verify the exact deployed bootloader and the
specific final firmware on hardware: cold boot, health confirmation, failed-health
rollback, reset/power loss, and unchanged NVS/appdata behavior. Fresh full device
readback, inactive pair writes and verification, separate OTA-selection sector
last, and no SD card deletion remain mandatory. No hardware access is authorized
by running these offline recipes.

Sources: [Arduino 2.0.17 S3 sdkconfig](https://github.com/espressif/arduino-esp32/blob/2.0.17/tools/sdk/esp32s3/sdkconfig),
[released Runtime bank store](https://github.com/michaelrolphone-cmyk/RiscRTE/blob/4107eaeedd8c801eeaf7deb1c7bc4a943cd27342/src/ports/esp32s3/NativeBankStore.cpp).

## Regression tests

```sh
python tests/test_native_idf61_candidate.py --runtime RUNTIME \
  --image-helper WATCH_HELPERS --sdk SDK --baseline RELEASED_FACTORY -v
```

The suite checks immutable baseline selection, exact payload preservation,
private imports in both symbol tables, corrupted/traversing artifact inputs,
mutable/dirty source refusal, deterministic packing, protected data regions,
new-bootloader/old-bootloader separation and torn-write fail-closed behavior.
