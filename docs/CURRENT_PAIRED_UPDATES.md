# Data-preserving updates for the current ABI2 Watch

The paired backend supports the `riscrte-paired-appdata-v2` layout. It updates one inactive firmware/store pair,
then require the default Clock to confirm health after restart. They never
repartition the device or install the initial empty app-data image.

The installed update provider 0.1.1 has a separate catalog parser defect: it
rejects Spectrum's required KV API1 and API2 entries as duplicate names. Provider
0.1.2 corrects this to reject duplicate `(capability, API)` pairs. Firmware OTA
clones the old provider and app OTA cannot replace it. The initial Watch 1.0.2
transition BIN installs provider 0.1.2 and the app-data layout. The user accepts
that one-time full flash erasing current test settings and samples. After it,
use the built-in paired updates to preserve NVS and app-data. Dropping a required
API is not a valid workaround. Preparation reports the starting-state limitation
explicitly; no Windows installer is required for the delivered transition.

Once a compatible provider is installed, install the compatible Runtime first,
restart successfully, then install the Spectrum app and restart. A firmware
transaction clones the current boot store without changing its contents. An app
transaction clones the current native image and replaces only the existing
authorized app ELF/manifest. Its requirement types, APIs and paths must match.
NVS/settings and app-data are outside the paired transaction's write set.

`scripts/prepare_current_updates.py` prepares the two release asset folders and
a proposed catalog update from an exact current Watch BIN, native candidate,
current app package and the user's prior ABI2 custody image. It verifies:

- source and artifact identities, all component hashes, layout and native ABI;
- native ELF rollback/TLS/DRAM proof and matching native bytes in the full BIN;
- unchanged Spectrum authority, board and boot policy;
- monotonic release/app versions and the actual installed catalog grammar;
- separate OTA assets containing only native firmware or Spectrum ELF/manifest.

It also retains the full initial USB image as a separately named release asset.
That full image overwrites NVS and app-data, so it is unsuitable for preserving
the user's existing room/event examples. No preparation command publishes a
release, changes the live catalog, connects to a device or flashes it.

The installed clients accept only the fixed Watch release-index URL and exact
immutable release-asset URLs. They cannot import a local folder/ZIP or a CI
artifact. Prepared inputs become usable on the Watch only after the matching
releases and catalog entries are explicitly authorized and published. The
current App Store also does not enforce a minimum Runtime version; the recorded
minimum is informational and the two-step install order remains explicit.

The final Watch CI retains its exact native candidate as `twatch-native-runtime`
alongside the full BIN. Use that candidate so native OTA bytes match the embedded
native image, rather than assuming separate builds of one source revision are
byte-identical.

The existing source-wired cross-layer update matrix now has an ABI2 mode. It
tests normal updates, cancellation/retry, malformed/corrupt/short responses,
authority rejection, retained cleanup, activation uncertainty and fresh-process
recovery at eight power-cut points. Native write/erase calls are limited to the
inactive pair and its journal sector, with non-erased NVS/app-data sentinels
preserved. The legacy ABI1 matrix remains separate. TLS, physical flash and
SPIFFS are simulated boundaries; physical OTA, power-loss and filesystem
qualification are still pending.
