# Watch 1.0.0 stable product

The owner accepted the exact integrated 0.5.2 build on 2026-10-04 and authorized
contributing merges, publication, and a separate Reader-style release index.
Product version **1.0.0** promotes those same bytes. It does not renumber Clock
0.5.2, Runtime 0.1.6, or shared packages. The source-controlled product identity
and accepted artifact/source pins are in [product.json](product.json).

The release is `firmware-v1.0.0`, with directly flashable
`twatch-s3-launcher-1.0.0.bin`. Its SHA-256 remains
`6f0cba6da17fce769d03807aefce44b0e5fc445d349b8b7dc0f6782d376d80c5`.
The original 0.5.2 flashing ZIP is preserved unchanged for custody and recovery.
Flashing at 0x0 replaces the lower 8 MiB including settings and saved Stopwatch
state; upper 8 MiB is untouched. Publication does not flash any device.

All seven exact configured applications are independent releases in this Watch
repository, including the directly downloadable **default.elf** core and its
matching default.json. App versions, compiled Watch configuration, licenses,
shared owning-source pins and exact bytes are retained. These are the ELFs inside
the accepted Watch image, not the differently configured generic shared builds.
The existing driver publisher produces independent immutable versioned packages.
The product publisher downloads them and checks every package against accepted
CI; the six installed driver ELFs/manifests must match the image exactly. Other
optional drivers are cataloged without claiming hardware qualification.

The dedicated [`release-index` branch](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/tree/release-index)
contains `release-index.json`. It follows Reader's schema 1: firmware object,
apps array, drivers array, immutable version/tag/asset/url/size/SHA-256 records,
plus component manifests. Updates are monotonic, reject same-version content
changes, preserve unrelated entries, and use a non-force branch push after every
referenced release is public and download-verified. Reader itself is untouched.

`Publish accepted Watch product` validates on the release PR and publishes only
from the repository's current default branch, after the existing driver
publication workflow completes successfully (or explicit manual dispatch). It
shares the driver's publication concurrency group. Assets are uploaded to drafts, downloaded and
hashed before publication; interrupted drafts resume only with identical bytes.
Published versions are never overwritten. Future product versions need a new
accepted product manifest and exact source/artifact evidence. Historical Actions
artifacts may expire; the published provenance ZIP remains the permanent source
of these released bytes. Missing frozen inputs fail closed rather than rebuild.

The old custody ZIP's pending-hardware text is historical build-time evidence.
Product provenance separately records owner acceptance of the exact integrated
Watch. This is not blanket qualification of all optional peripherals, CAM/X4,
power consumption, or future component builds.
