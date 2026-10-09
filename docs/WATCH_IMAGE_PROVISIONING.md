# Initial Watch 1.0.17 provisioning

This recipe installs the complete 23-app Watch store, including Contexts and the
qualified Audio/Waterfall cleanup correction. It uses stock RiscRTE 0.1.73 at
`b587df55298e0bb8e676b3d59ca13679c0267bf7`, with the Watch's policy16, radio-IQ
reservation and disabled app-input cache. It is an **initial installation** for a
new 16 MiB Watch. The resulting full image overwrites NVS and app-data. Use the
separate preserving-update workflow for an existing device.

The generic seed has only the baseline board, an empty provider graph and the
heartbeat ELF. The owner profile selects one immutable HTTPS image containing
all 95 product files: the real `board.json`, complete boot graph, drivers,
manifests, apps and `default.elf`. No product application is omitted to make the
store fit. The compact image has eight entirely free SPIFFS blocks, above the
Runtime's four-block admission reserve. Schema1/2 file provisioning retains its
existing conservative streaming limit; this dense store uses additive schema3.

## Public inputs and source custody

The payload directory is `provisioning/watch-1.0.17/`. Its six files are:

- `image.bin`: exact compact product SPIFFS image
- `seed.zip`: generic native seed, linked ELF proofs and bank0 receipt
- `LICENSES.zip`: product and native notices
- `binding.json`: app-stage/native binding, including all file hashes
- `payload.json`: complete source, capacity and production admission receipt
- `COMPLETE`: completion marker, written after the other files pass readback

The adjacent deployment directory supplies `inventory.json` and
`deployment.json`. Every download URL contains the actual immutable payload
commit. `bind` refuses moving refs, tree objects, changed blobs and extra files.
`verify-endpoints` downloads all six files over validated HTTPS, refuses
redirects, and repeats the exact native/store admission checks.

Original Watch build commits are retained in the Watch-only source bundle and
source receipt under `docs/provisioning/watch-1.0.17/`. Restore those objects with
`git bundle unbundle` before checking a receipt from a fresh clone. The canonical
publication commit can differ from an original build commit; the receipt maps
their exact source trees without changing the firmware or cohort identity.
Executable helpers and native admission fixtures must match the frozen recipe;
only publication payloads, documentation and workflow records may be added.

The final bounded-input recipe was reconstructed and requalified on the public
`c0f730445c772f14b38ace627784e36a30795de7` checkpoint after its unpublished source
archive was lost. Its new source revision is recorded in `payload.json`; it does
not claim to reproduce the unavailable `f2eae968c8c34e238188159cb567dda2ca21087c`
commit or archive. The published native seed, product image, binding and licenses
retain their exact original bytes. The reconstructed wrapper snapshots bounded
binding inputs before invoking the original binder, including refusing compressed
license entries and limiting store paths, files, individual sizes and total bytes.

Recompiling the app stage also requires its exact separately pinned System,
Utilities, Productivity and Drivers sources. At preparation time the new
Contexts model-client header dependency had not yet been published. The checked
binary payload and its original source IDs are retained; this document does not
claim a remote-only app rebuild until that dependency is available. Existing
already-published source bundles remain valid.

## Prepare the private JSON and initial image

Run these steps on the owner's computer. Python 3.11 or 3.12, the pinned Python
requirements, a C++17 host compiler and the official IDF4.4.7 NVS generator are
required. The Runtime verifies the NVS generator's exact SHA256 before using it.
The generator is available from the official Espressif repository:

https://github.com/espressif/esp-idf/blob/v4.4.7/components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py

1. Check out the exact Runtime source above and the published Watch recipe.
   Restore the Watch source bundle, then run the Watch endpoint verifier using
   the published deployment directory.
2. Unpack the verified `seed.zip` into a new local directory. Keep a private work
   directory outside all Git checkouts and publication folders. Create its
   `wifi.json` with the owner's `ssid` and `password` fields locally. Credentials
   are never needed for public payload generation or endpoint checks.
3. Build the production owner-input validator:

   ```sh
   bash "$RUNTIME/scripts/build_provision_input_tool.sh" "$PRIVATE/provision-input"
   ```

4. Create the actual private schema3 provisioning JSON and NVS inputs:

   ```sh
   python "$RUNTIME/scripts/provision_profile.py" profile \
     --inventory "$DEPLOYMENT/inventory.json" \
     --wifi-file "$PRIVATE/wifi.json" \
     --validator "$PRIVATE/provision-input" \
     --time-server "$TIME_SERVER" --output "$PRIVATE/owner"
   ```

   `$TIME_SERVER` is the owner's chosen reachable time server. The output includes
   `profile.json`, validated by the same native parser used during installation.
   The JSON pins every installed file and the complete image. It remains below
   the native 16 KiB profile limit with the supported Wi-Fi field bounds.

5. Compose the private full 16 MiB seed image with that profile in NVS:

   ```sh
   python "$RUNTIME/scripts/provision_device.py" \
     --seed "$SEED" --owner "$PRIVATE/owner" \
     --validator "$PRIVATE/provision-input" \
     --nvs-generator "$NVS_GENERATOR" \
     --output "$PRIVATE/first-install" --new-device
   ```

   `first-install.bin` is the generic firmware plus owner configuration. It
   contains credentials and must stay private. These commands do not access or
   flash a device. Install that image only through the separately authorized
   initial-device procedure after checking the actual hardware/layout.

## First boot and recovery

On first boot, the native bootstrap validates the private profile, joins Wi-Fi,
obtains time for TLS verification and downloads the pinned compact image to the
inactive store bank. It checks download length and SHA256, rereads the whole raw
image, validates the physical SPIFFS layout before mounting, and verifies every
file, board declaration, provider graph and ELF against the paired native.
Only a fully admitted pair can be selected for the next boot into the Watch's
default application. The existing journal, consumption receipt, rollback and
confirmation rules remain in force.

A failed or interrupted download keeps the current selected pair. A subsequent
attempt restarts with the original pinned image. Retained cleanup and uncertain
selection states fail closed; they do not claim installation success or format
the store. NVS and app-data are untouched by the download/install phase. The
separate initial full-image operation is the step that initializes those areas.

## Verification and limits

`scripts/test_watch_image_provisioning.py --runtime "$RUNTIME" --payload "$PAYLOAD"`
checks the real native/store, changed and rehashed inputs, exact source custody,
ZIP/directory bounds, interruption cleanup, completion ordering and immutable
Git identities. Runtime tests additionally exercise real pinned SPIFFS readback,
short reads, corrupt images, missing/extra files, interrupted installation,
retry, admission refusal, retained cleanup and selector uncertainty. The Watch
Clock/Contexts and selected Bluetooth/HID lifecycle tests use the exact bound
23-app cohort.

Host tests and target builds do not establish physical Wi-Fi, RF, power-loss,
flash timing or board behavior. Hardware provisioning remains unrun. Watch
1.0.12 and the historical 1.0.7 provisioning payload are separate preserved
cohorts; this candidate does not rename either one or migrate existing data.
