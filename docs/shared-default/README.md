# Shared default package contract

The shared-default release preserves the released alarm-sleep product inventory,
including every unrelated native-resolution application and provider ELF. Only
`default.elf`, `default.json`, `boot.json`, and `cohort.json` may change in the
installed store. The Runtime firmware is rebuilt from the pinned shared-provider
integration.

The canonical Watch build is common to both products. Product routing resides in
boot policy: both products grant preferences namespace 1. Waveshare additionally
maps generic file namespace 12 to the unchanged sdmmc-fatfs volume 12 provider;
TWatch leaves the optional file capability unavailable. Other app policies,
board selection, provider configuration, settings namespaces, native watch-face
payloads and alarm service bytes are preserved exactly.

`package_shared_default.py` creates a staging store and an extraction proof. It
verifies the exact released factory/store inventory and two matching canonical
builds, then round-trips the new store. This staging command alone does not
produce a firmware-qualified factory image.

## Qualified integration and release production

The shared-provider Runtime source is pinned to
`e697c3677eca661892517c2bf4c0c6b2f764985c`, merged in Runtime 0.4.4 at
`d567c81bdc939c2ccce6858aa650fbf094757e8a` with the same qualified source tree.
Both broad host jobs, focused provider regressions, strict GCC 15 target checks,
and fresh SDK 6.1 native product preflights passed. The official product
preflight receipts are:

- [T-Watch native preflight](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/actions/runs/38874706996)
- [Waveshare native preflight](https://github.com/michaelrolphone-cmyk/RiscRTE-Wavshare-S3-Touch-AMOLED-2.06/actions/runs/38874746179)

These preflights cover fresh same-process native build custody, admission of
every production ELF in normal and sanitized runs, native/store bank binding,
preservation fault models, and cross-product extraction. Both final factories
contained the same 616752-byte default ELF, SHA256
`b60579dddf0123907e11b6c3ec862e28c76547482bcc325de349e55f06db2dd6`.
Independent extraction also preserved every unrelated installed payload and the
released alarm ELF.

`source-pins.json` now enables release publication. The versioned release branch
runs `shared-default-native.yml` to rebuild and qualify its exact commit, generate
the source-bound 16-asset release, and publish only after complete byte
verification. Preflight success does not substitute for that final release run
or the subsequent independent public-asset audit.

## Installation and hardware status

The factory image is a full-flash image and erases saved data. Back up first.
No data-preserving update kit is supplied by this release recipe. Standalone
firmware and store assets are verification inputs, not independently flashable
upgrade instructions. Use the release's `TESTING.txt` for the exact factory
installation command and device checks.

Physical-device qualification remains unperformed. Software/native build and
public-byte verification must be reported separately from actual hardware
behavior; no measured device timing, PSRAM pressure, or persistence result is
implied by host tests.

The historical alarm-sleep and native-IDF61 recipes/contracts are frozen by hash.
The new recipe must never relax their unchanged-native or alarm-only assertions.
