# Shared default package contract

This candidate workstream preserves the released alarm-sleep product inventory,
including every unrelated native-resolution application and provider ELF. Only
`default.elf`, `default.json`, `boot.json`, and `cohort.json` can change.

The canonical Watch build is common to both products. Product routing resides in
boot policy: both products grant preferences namespace 1. Waveshare additionally
maps generic file namespace 12 to the unchanged sdmmc-fatfs volume 12 provider;
TWatch leaves the optional file capability unavailable. Other app policies,
board selection, provider configuration, settings namespaces, native watch-face
payloads and alarm service bytes are preserved exactly.

`package_shared_default.py` currently creates a staging store and an extraction
proof, explicitly not a firmware-qualified image. It verifies the exact released
factory/store inventory and two matching canonical builds, then round-trips the
new store. No flashable factory image is produced by this staging command.

Final release gates remain closed pending the combined Runtime pin, fresh
same-process native build custody, complete production-loader admission (normal
and ASan/UBSan), native/store bank binding and preservation fault models, and
cross-product extraction of the identical default ELF/manifest. Hardware results
remain separate. No device access or preserving update kit is implied.

The historical alarm-sleep and native-IDF61 recipes/contracts are frozen by hash.
The new recipe must never relax their unchanged-native or alarm-only assertions.
