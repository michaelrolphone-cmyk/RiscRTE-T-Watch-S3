# T-Watch 1.1.43 payload preparation and admission gap

The complete delivered release is inventory-qualified. **No usable generic
serial-payload pair can be emitted from this release's present admission.**
The findings apply to the delivered 1.1.43 firmware. Physical qualification is
pending.

## Exact release and complete inventory

- Product: `RiscRTE-T-Watch-S3`, `test-shared-default-1.1.43`, upstream release
  **415195233**, source `aa91c1cd7eb664d9a5bd78df05cab53b2c683f18`.
- Catalog release revision **2**, profile `watch` revision **0**, checked
  2026-10-16. Its supported factory asset is
  `TWatch-1.1.43-Shared-Default-factory-erases-data-0x0.bin`, offset 0,
  16,777,216 bytes, SHA256
  `f6b600197087ae93c93752507b89d6be0c248abb528c010da2d280f7a0166f36`.
- Runtime: `21c6d64c51470158e1e8fb26d403b194f27ea38c`, delivered version 0.4.5.
- All **16** public assets were downloaded independently and checked against
  published lengths and SHA256 hashes. `baseline.json` records every asset,
  every store file, every flash partition, and exact source evidence links.
- The factory's `bootfs0` slice is exactly the public `store.bin`:
  **121 files, 4,957,966 bytes: 59 ELFs and 62 JSON files**. Its 26 application
  manifests and 33 distinct driver manifests resolve all 59 executables
  internally. Boot has 26 application policies and 34 driver instances because
  the I2C provider is instantiated twice. No executable is missing or orphaned.
- There are **zero `image_source` declarations**, no boot `installation`
  admission, and no application `storage.files` / `storage.volume` grants.
  All existing applications, including LoRa, remain internal. The three other
  JSON files are `boot.json`, `board.json`, and `cohort.json`.
- Factory AppData is the exact **empty** 524,288-byte LittleFS image, SHA256
  `5f03c248f2de31c4da9ae8d9bc2033df064cee5e37694a9982f70fbb2f1d2ef0`.
  The pinned core generator was compiled, generated/remounted an empty filesystem,
  and reproduced those bytes exactly. `empty-appdata.json` records that proof.
  It is host-core evidence, not a native adapter or physical-flash test.
- The existing published normal/sanitized 59-ELF production-loader receipts were
  identity-checked against the exact delivered native ELF, all 23 native evidence
  artifacts, seven relevant compiled Runtime units, and the actual serial compile
  selection. They were not rerun here. All 117 unrelated store files remain
  byte-identical to the release's frozen predecessor inventory.

## Actual writable namespace and consumers

The native profile explicitly selects `RISC_NATIVE_SERIAL_FILES=1` and
`RISC_NATIVE_SERIAL_APPDATA_FILES=1`. Its sole serial namespace is **2**, bound by
`NativeSerialStorage.cpp` to a distinct `ReopenedFiles` provider rooted at
`/appdata/.serial-files`. No boot-store export or SD serial provider is selected.

That serial ID is unrelated to an application AppData instance ID. Production
`AppDataFiles.cpp` resolves application namespaces below `/appdata/n%08lx`, while
the serial provider is confined to `/appdata/.serial-files`. Sharing the physical
partition does not create a consumer route. Existing storage grants and runtime
configuration provide no application consumer of this private serial workspace.
The active paired boot bank remains immutable through serial operations.

A path copied to private namespace 2 therefore does not install or replace the
existing application/store payload. File-browser installed-file or app-data-export
capabilities do not change the serial provider's root or authority. Generic payload destinations require explicit provider admission and a matching
target consumer.

## Why no paired manifest is emitted

The actual firmware-associated payload is the **entire internal store already
carried by the factory image**. There is no separately published companion asset
or required serial-consumed file. The frozen payload 1.0.0 schema requires at least
one volume and one file. An empty payload, synthetic placeholder or archive of the
boot store addressed to private namespace 2 would not be a usable paired candidate.

A usable serial-payload pair requires real required files, an admitted writable
generic destination and a consumer of those exact files after the final flash step.
Those technical mappings are absent from the delivered product.
The catalog's installer implementation remains owned by the website builder.

Even after product mapping exists, the current catalog records do not supply the
trusted generic installer method ID, accepted hardware revision bounds, namespace
capabilities/write budgets, or immutable manifest/container association. Preserve
these as missing inputs rather than minting values from labels or source constants.

## Flash order and preservation

The existing supported full factory image supplies the internal firmware/store
pair together. It replaces settings/internal data: NVS is erased and AppData is
replaced by its empty image. The second application and boot-store banks are erased;
boot-selection metadata is initialized. No data-preserving update kit is supplied.
Do not flash standalone firmware/store assets independently.

For a future legitimate factory-plus-serial pair, use **firmware → payload → full
readback and consumer verification** unless the exact method has independently
proved preservation for a different order. Re-establish target firmware and actual
namespace availability after flashing. Files transferred into AppData before this
factory image would be erased. Applying the present private namespace after flash
still does not make its files usable by existing applications.

Serial work remains per-file, preserving unrelated files and directories. Replace
is explicit, destructive and non-atomic; no folder replacement or formatting is
introduced. Namespace availability, storage capacity, safe foreground checkpoints,
full acknowledged COMMIT/CRC and SHA256 readback require the actual installer flow.
BUSY, UNAVAILABLE and I/O/retained-custody failures are not file absence.

Product publication and physical qualification remain behind the recorded X4 then
Waveshare qualification sequence. This audit's pass does not satisfy either gate.

## Reproduce the checks

Use Python 3.10+, Git and the exact public asset folder. The Runtime repository must
contain the delivered Runtime commit above and frozen contract commit
`788c8640906a3baf90a68be33f2253bd05a0bc8c`. The product repository must contain the
original release commit. Source reads use immutable Git objects, not current files.

```sh
python scripts/audit_catalog_payload.py \
  --assets /path/to/1.1.43-assets --runtime /path/to/RiscRTE \
  --download --output /path/to/audit.json
python scripts/test_catalog_payload.py \
  --assets /path/to/1.1.43-assets --runtime /path/to/RiscRTE -v
```

The 27 tests include all 16 individually corrupted assets, missing/extra assets,
checksum ambiguity, source mismatch, invented application/driver routes and grants,
missing/orphan executables, traversal, policy coverage, empty schema, false hardware
claims, source-linkage changes and forbidden candidate/publication switches.
`--require-paired` intentionally rejects the audited release. It writes only the
factual audit report, never a payload manifest or container. Python `-O` is rejected
by the pinned SPIFFS decoder; no assertion-stripped extraction is accepted.

To repeat the separately recorded empty-image proof, use the delivered Runtime
checkout and LittleFS commit `f53a0cc961a8acac85f868b431d2f3e58e447ba3`:

```sh
python /path/to/RiscRTE/scripts/app_data_image.py \
  --littlefs-source /path/to/littlefs --output /path/to/new-empty-image
```

Compare `appdata.bin` byte-for-byte with factory `[0x270000:0x2f0000]`. The generator
checks exact LittleFS source hashes and remounts the generated image. The committed
CI support repeats this proof as well as the audit and tests.
