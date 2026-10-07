# Provision the accepted Watch 1.0.7 from a generic seed

This initial-install profile downloads the unchanged **accepted Watch 1.0.7**
feature set after a generic Runtime seed boots: 22 applications, 21 provider
images, the real board configuration, and the configured Clock default. All 89
store files and 43 Xtensa ELFs remain byte-identical to the accepted release.
This is separate from the 1.0.8 RF Spectrum candidate and later power repairs;
it is not a new/latest product release or an existing-device OTA update.

## Pinned public inputs

- [Complete immutable file inventory](../provisioning/deployments/watch-1.0.7/inventory.json)
- [Deployment record and seed/archive checksums](../provisioning/deployments/watch-1.0.7/deployment.json)
- [Exact generic seed ZIP](https://raw.githubusercontent.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/a944c3828075eb2fa35188e7850a6ab18a79e7e2/provisioning/watch-1.0.7/seed.zip)
- [Frozen product payload](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/tree/a944c3828075eb2fa35188e7850a6ab18a79e7e2/provisioning/watch-1.0.7)

The complete store's URLs are pinned to commit
`a944c3828075eb2fa35188e7850a6ab18a79e7e2`. Keep the inventory unchanged when
preparing the private owner profile. The seed ZIP is 8,093,772 bytes with SHA-256
`fdb7c400dc81e17923ca6f00c6866065724817c4972b41aa4e80e73337e696cd`.

## Exact native and seed custody

Runtime source is `4a0891fc0ec10dcd100c6248768cabecaafec888`, version 0.1.41,
target `esp32s3-16mb-appdata-iq`, paired app-data ABI2. The seed must contain the
exact accepted native candidate, not merely another build with that version:

- Firmware: 1,238,288 bytes, SHA-256
  `776748a2331f6f6c5de0fc769bd13c8731c503a026217a767a18e86bac37dc3b`
- Native ELF: 19,806,564 bytes, SHA-256
  `426b85cdfd68b21a8acbbf20c489bed67b2b7f2b234549fb9944f4ff2518085f`
- Candidate manifest SHA-256:
  `2d9dc26eecc81eb74b9357b6972913a753c4db840a5f8bab4566b02447af805b`

These recovered assets reproduce the accepted Watch candidate exactly. A
same-source hosted build has a different native hash (`2ab3b0f3...`) and is
correctly refused. No cohort or boot-policy rebinding is needed with the exact
accepted native. The earlier exploratory 1.0.9 recipe is not this deployment.

Runtime's existing `provision_seed.py` composes the generic, three-file
heartbeat store with the verified accepted native candidate, exact paired
partitions, rollback bootloader, linked IQ proof, fresh empty app-data, journal
and OTA selector. NVS and credentials are deliberately absent. The resulting
public `seed.zip` is frozen alongside the product's individual download files.

## Public preparation

Use Python 3.11 and the pinned validation dependencies `esptool==4.11.0` and
`pyelftools==0.32`. Keep an unmodified Runtime checkout at the exact source above.
Download the already-published
[accepted store](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/releases/download/firmware-v1.0.7/accepted-store.zip)
and [licenses](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/releases/download/firmware-v1.0.7/LICENSES.zip)
into the same input directory. Their required SHA-256 values are:

- Store: `d7df281cd6bb35f833d7b1bfff25199d0d8d2d890e2c5cf3bb7585007a6f7572`
- Licenses: `80c78794f8ea969cc831ca6e774dfa497b484ad3937e3a49d6778d540177aebc`

The preparation tool verifies those exact bytes; it performs no download or
publication implicitly. From a committed Watch checkout:

```sh
python scripts/watch_provisioning.py --runtime "$RUNTIME" freeze \
  --archive "$INPUTS/accepted-store.zip" --seed "$VERIFIED_ACCEPTED_SEED" \
  --source "$(git rev-parse HEAD)" --output provisioning/watch-1.0.7
python scripts/watch_provisioning.py --runtime "$RUNTIME" verify \
  --archive "$INPUTS/accepted-store.zip" --payload provisioning/watch-1.0.7
```

Commit the public payload on its separately authorized branch, then bind the
inventory to the actual full 40-character payload commit:

```sh
python scripts/watch_provisioning.py --runtime "$RUNTIME" bind \
  --archive "$INPUTS/accepted-store.zip" --payload provisioning/watch-1.0.7 \
  --revision "$PAYLOAD_COMMIT" --output provisioning/deployments/watch-1.0.7
```

Binding compares every payload file against that existing Git commit before
constructing immutable HTTPS paths. A moving branch, missing commit, changed
file or mismatched seed is refused. After publication,
`verify-endpoints --deployment provisioning/deployments/watch-1.0.7` downloads
and checks all individual store files, seed and licenses, refusing redirects.
It is read-only and never contacts a device.

The public inventory contains no Wi-Fi fields and is not an installable owner
profile. No private input, NVS image or complete private flash image belongs in Git.

## Private owner preparation

Use the verified deployment's immutable inventory and `base_url`, plus its exact
`seed.zip`. Extract the seed into a new local directory. Follow the
[pinned Runtime first-install instructions](https://github.com/michaelrolphone-cmyk/RiscRTE/blob/4a0891fc0ec10dcd100c6248768cabecaafec888/docs/FIRST_INSTALL.md):

1. Build the production `provision-input` validator.
2. Outside Git, supply real Wi-Fi input and an explicit time-server choice. Run
   `provision_profile.py profile` with this inventory and exact common base URL.
   It emits the bounded schema2 private owner input.
3. Run `provision_device.py` with that input, the exact seed, the hash-verified
   official NVS generator, and the mandatory `--new-device` acknowledgement.

The private full image is only for a **new 16 MiB device**. It replaces NVS and
app-data and must never update an existing Watch. Preparation grants no hardware
flashing permission. Confirm the physical board, BMA423 motion configuration,
radio hardware/antenna and layout separately before any installation.

On boot, native station/SNTP/verified HTTPS primitives fetch the full pinned
inventory, including `board.json`, before product providers exist. Whole graph,
ELF and readback admission precede inactive-pair selection. The next boot runs
the selected Clock with its ordinary app-health/rollback contract. Downloads
cannot start until the owner supplies the private inputs.

## Qualification and limits

Focused tests cover exact accepted-byte preservation, native mismatch refusal,
seed integrity, reproducibility, no-overwrite and symlink bounds, interruption
cleanup, complete inventory and exact commit pinning. Production admission
checks all 43 target ELFs against the exact native ELF's public export tables,
with zero hardware/storage callbacks, and rejects corrupt apps/providers/boards.

The pinned real-SPIFFS harness streams the complete 89-file store using repeated
4096/512/37/1-byte inputs. It covers hash/readback corruption, write failure,
interrupted remount/retry, admission refusal and unchanged active bytes. Generic
native bank tests cover bootstrap downloads, consumed-profile receipts, offline
fallback, rollback, retained cleanup, uncertain selection and NVS/app-data
preservation. The product-specific native bank IQ test fixture needs a separate
test-only lifecycle callback repair; production Runtime code is unchanged.

Host tests do not execute Xtensa instructions or physical hardware. They do not
qualify physical Wi-Fi/TLS, boot-to-Clock execution, flash power cuts or battery
current. The original product's reported SDR acceptance does not qualify this
new provisioning route automatically.
