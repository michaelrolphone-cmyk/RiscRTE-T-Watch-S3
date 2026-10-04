# Paired Firmware Update and App Store development lane

This lane is an explicit migration candidate. It does not publish a release,
change the production release index, flash hardware, or make the delivered
8 MiB factory deployment OTA-capable. Physical verification remains pending.
The current production 1.0 release-index record remains USB-install-only.

## Compatibility and migration boundary

The source-pinned Runtime 0.1.11 target is `esp32s3-16mb-paired`, layout
`riscrte-paired-16m-v1`, store ABI 1. Migration requires a separately verified,
explicitly user-controlled full 16 MiB reflash. Its offsets are:

| Pair/metadata | Offset | Capacity |
| --- | --- | --- |
| app0 | 0x10000 | 0x300000 |
| bootfs0 | 0x310000 | 0x4f0000 |
| app1 | 0x800000 | 0x300000 |
| bootfs1 | 0xb00000 | 0x4f0000 |
| otadata | 0xff0000 | 0x2000 |
| bank_state | 0xff2000 | 0x2000 |

The lower firmware/store offsets match the existing installation, but that is
not permission or a safe method to migrate over OTA. The upper 8 MiB is now used.
The running OTA subtype selects its matching immutable store. Firmware Update
clones the existing store with a new Runtime image. App Store clones the existing
Runtime with only already-authorized app ELF/manifest replacements. Neither may
replace board wiring, grants, drivers, or create new application authority.
The health-confirming Clock manifests are version 0.7.1. Native rollback remains
pending until successful default application startup and first-frame completion.

## Exact authority

There are separate `ota_update` and `app_store` apps. Each has exactly eight grants:
display instance 5, touch 6, RTC API 2 instance 8, battery 4, key-value namespace 6,
Wi-Fi instance 15, its own kind-specific update service instance 0, and alarm
service instance 0. Saved Wi-Fi credentials stay in namespace 6. UTC supplied to
TLS is derived from the existing fixed UTC+08 RTC basis by subtracting 28,800
seconds; the RTC/display configuration is not rewritten.

The ordinary ELF providers export `software.update.firmware@1` or
`software.update.apps@1`. Only providers consume `platform.http-client@1`,
`platform.bank-store@1`, and `platform.clock@1`; apps never receive those native
tables. Providers are packaged at `update-fw` and `update-apps` so every SPIFFS
object path, including its leading slash, remains below 32 bytes. No provider
gets an app KV namespace or raw radio authority.

## Build and verification

The exact four dependency revisions are in `apps/update-sources.json`. Each must
be a clean checkout. Set `TWATCH_CC` to the existing pinned Xtensa GCC 8.4 compiler.
For `MODE`, use `paired` (health-confirming baseline), `ota` (Firmware Update), or
`all` (both apps). Build and verify each stage separately:

```sh
python scripts/build_twatch_drivers.py
python scripts/build_update_apps.py --system-apps SYSTEM --utilities UTILITIES \
  --runtime RUNTIME --productivity PRODUCTIVITY --mode MODE
python scripts/build_update_deployment.py --mode MODE
python -m unittest discover -s tests -p 'test_update_deployment.py' -v
python scripts/build_update_common.py dist/update-launcher-deployments/*.zip \
  --pr-head-sha EXACT_WATCH_HEAD
python scripts/build_update_store.py dist/update-common/*.zip --mkspiffs PINNED_TOOL
```

All modes use the separate `dist/update-launcher` staging directory. Archive or
copy a completed stage before building the next one. No old clock, alarm, Points,
or Wi-Fi lane is selected or rewritten by these commands. The deployment builder
also exposes `updates=None` for all frozen historical lanes, `updates=()` for the
paired-only lane, and ordered OTA/both selections. Every staged build requires all
eight explicit source profiles; no hardware variant is guessed.

`update-preservation-baseline.json` records actual verified 216e2d73 CI ZIP hashes
and all 44 original store files. All existing app/driver/service bytes are checked
unchanged except the explicitly health-enabled default Clock, Springboard
catalog, and boot policy additions. The returning Clock ELF is also byte-identical. Existing manifests remain exact
except the two Clock versions moving to 0.7.1 and the exact pinned Springboard
version for its new catalog entries. Provider sources, target ELF imports/exports, bounded BSS/stack,
package hashes, catalog/return targets, full app grant lists, and paired layout are
independently checked. Rehashing a modified archive does not bypass these checks.
The common archive changes only `board.revision`; it carries enough provenance to
reconstruct all eight original deterministic ZIPs and verify their original hashes.
SPIFFS packing uses the existing pinned tool and verifies every unpacked byte.

The Runtime requirement record initially says `awaiting-exact-source-ci-artifact`.
That is source intent, not firmware artifact custody. A final flashing bundle must
separately verify the exact successful Runtime CI artifact, partition table,
rollback-enabled bootloader, compiled source/version markers, TLS root bundle,
paired journal seed, and complete store. These scripts alone do not certify a
firmware BIN, hardware acceptance, migration success, or production release.
