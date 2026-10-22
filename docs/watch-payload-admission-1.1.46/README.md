# T-Watch 1.1.46 source-only payload admission audit

Status: **UNQUALIFIED source checkpoint**. The current-release matrix and bounded
regression audit are being prepared. No successful CI, installable payload,
firmware rebuild, target execution, or hardware qualification is asserted.

## Exact scope

- Base: `81dbde86969615f7378cc03c5800960a9092e076`.
- Release: `test-provisioning-1.1.46`, public release ID `415753487`,
  producer `ab9ff33975680c5bb8d9a2e7ed346d0300732a4e`.
- Complete core feed:
  [immutable source](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/blob/c2ea463a0bff968ce38e2a270aedfae7c49fefb4/native-packages-v1.json).
- Runtime: `48229bd1593a2e24e95bf4537b495ee615990fd3`, version `0.4.11`.
- Planned additions only: this directory, `scripts/watch_payload_1146_audit.py`,
  `scripts/test_watch_payload_1146_audit.py`, and
  `.github/workflows/watch-payload-1146-audit.yml`.

The deliverable is a complete 125-row inventory/consumer matrix with exact
declared sizes and hashes, source identity checks, path/inventory integrity
checks and fail-closed rejection of a generic serial pair. Release metadata,
feed and source evidence must remain distinct from freshly downloaded binary
verification. The existing complete feed and factory delivery remain unchanged.

## Admission boundary

Every core file belongs to the firmware-owned internal store. No admitted RTEF1
destination or usable generic serial-payload pair is established. Empty
`apps[]` is the separate dynamic package catalog, not a missing core bootstrap.
The private serial namespace, package volume and application AppData roots
must not be aliased. Partition/reserve observations are not installer budgets.

The historical 1.1.43 audit remains unchanged. This work does not create a
storage implementation, alter accepted pins or production bytes, emit a
payload manifest/container, change releases/tags, merge, deploy or access
hardware. Paired-catalog publication and physical qualification remain gated
by the recorded Waveshare pass.

## Publication-trigger inspection

Existing workflows were inspected at the exact base before creating this
branch. Firmware publishers are restricted to main/master, named release
branches, explicit dispatch, or gated workflow-run events. This source-only
branch matches none of those push routes. This directory deliberately does not
match the historical `docs/catalog-payload/**` audit trigger. A separate
read-only, bounded audit workflow will qualify the published head. Inherited
general PR checks may also run; they are not hardware qualification.
