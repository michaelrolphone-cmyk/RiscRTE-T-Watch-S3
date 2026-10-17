# T-Watch 1.1.46 delivery evidence

The released image delivers the exact common Home 0.20.1 already shipped in
Waveshare 0.1.59. All software evidence here is separate from physical acceptance.
Hardware has not been tested. The factory image erases saved device data; no
preserving update kit is supplied.

## Immutable source and release

- Producer: `ab9ff33975680c5bb8d9a2e7ed346d0300732a4e`
- Reviewed PR: https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/pull/82
- Merged main: `2f7c1c1b7b5d0e0f0bb072bdb89da85a754fd482`
- Producer and merged main tree: `07ba6e60526aa7d9b78d06bd37f75269263c75b5`
- Release: https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/releases/tag/test-provisioning-1.1.46
- Catalog ID: `RiscRTE-T-Watch-S3:test-provisioning-1.1.46`, revision 1

The 1.1.45 producer and all 19 public baseline assets remain unchanged.
The final 125-file store retains 122 unrelated payloads and 60 ELFs exactly.
Only Home ELF, its version-only manifest and native cohort identity differ.
Settings and all boot capability authority remain unchanged. The complete
125-file credential-free core feed is paired to the delivered native firmware
and store; its separate dynamic application list is empty.

## Final delivered bytes

`publisher-public-byte-receipt.json` records all 19 complete public downloads and
their byte equality to artifact 12097969226, archive SHA256
`59ac4cbd0896797f024c450ea08a4d41161ff97341af38afe793885e6f65ac2d`.
That artifact was produced by run 39026555734 attempt 1 and reused without a
rebuild by publisher-only attempt 2. Immediate draft-list readback failed after
creation on attempt 1; the exact-source empty draft was verified before retry.
No tag or asset replacement was used.

- Home: 554744 bytes, SHA256 `f376d722b07c52184cf4cd27df306054920cdf742ccb8bdd4d476a08e35aef54`
- Factory: 16777216 bytes, SHA256 `e132a6276cd444cd41482ecfcc2043296b2acf02ef882acc83ba1af4c76edff6`
- Native ELF: SHA256 `6bf06b099b3d77e28150e2af5933d5a08427383fb9724ed4bb30316c8867d227`
- Feed: SHA256 `2f08c10587344d3eb2ae07967a990ec1102719c9298582daa60037bd470549c3`

`public146-audit.json` verifies full release custody, final factory extraction,
paired feed, shared Home identity and retained payloads. The catalog independently
downloaded the complete factory image and verified its size and SHA256; see
`catalog146-verify.json`. This is download validation, not a device flash or
physical acceptance.

## Actual linked native proof

`public146-memory-independent.json` recomputes IQ reservations and DWARF/workspace
placement from the actual final ELF in the public evidence ZIP. Its hash matches
the source lock. A separate reviewer recomputation is recorded in
`parent-public146-linked-audit.json`.

The heap-to-IQ gap is 7936 bytes, 16 bytes below the 1.1.45 value. The 64 KiB IQ
bank remains reserved. Linked Runtime size is 327224 bytes with 32 platform slots;
the internal package workspace is 15208 bytes. Static boot-view and serial
workspaces remain in `.ext_ram.bss`. These static proofs do not establish physical
dynamic heap availability, RF behavior or device liveness.

## Runtime behavior and predecessor controls

Runtime `48229bd1593a2e24e95bf4537b495ee615990fd3` (0.4.11) provides the exact
appended native sleep ABI plus RAM-only serial control progress during generic
internal storage custody. Internal-only package discovery can share AppData and
background-resource ownership with the private serial route. Strict paired-boot
confirmation storage vetoes remain intact.

The six `run_*` logs preserve complete local normal (`-0`) and ASan/UBSan (`-1`)
suite outputs for serial files, native provider custody and diagnostic checkpoint
behavior. `qualified-runtime-ci.log` preserves the same six-suite CI output from
the exact producer. `runtime-compatibility.json` records identical ABI/header and
append-only compilation checks. `runtime-predecessor-controls.json` records
rejection of 0.4.8's missing sleep ABI and 0.4.9's absent generic serial control
progress. Production-loader admission separately passed all 61 ELFs normally and
under sanitizers, including the retained ownership rejection/control cases.

## Candidate and final build distinction

Files beginning `qualified146-`, `parent-independent-linked-audit.json` and
`qualified-runtime-ci.log` refer to feature-branch run 39025819911. They establish
initial qualification, not public native-byte identity. The release branch has
its own source-bound native build receipt, ELF and factory hashes. Only files
beginning `public146-`, `parent-public146-linked-audit.json` and the publisher byte
receipt establish final delivered native bytes. The common Home ELF is identical
in both builds and to Waveshare 0.1.59.

The producer PR's driver regression run 39025853560 passed all 10 jobs before
merge. Post-merge regression runs are recorded separately in `delivery.json`;
their status does not convert software evidence into physical acceptance.
