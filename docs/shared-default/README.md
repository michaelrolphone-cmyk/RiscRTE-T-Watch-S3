# Serial-enabled shared default candidate 1.1.43

This source-only candidate uses the existing fresh-build, exact-source shared-default
release machinery. Source pins are finalized; publication is disabled. Runtime is
`21c6d64c51470158e1e8fb26d403b194f27ea38c`; Watch is
`8132d73c828c0e4763f6c89a3d6a4a883314056a`. Fresh full native qualification
and release enablement remain required. A source pin or previous qualification
receipt alone does not qualify this candidate.

The common Home 0.18.0 default is identical for both products: 617424 bytes,
SHA256 `9f10c7150cdc175ff5af0dbc1410e455ead4f18868dd56555e10860781103f2f`.
Its ordinary owner loop uses the settled Runtime serial checkpoint. The manifest
SHA256 is `0888f82c0f69d48210d94bd9507e359833200d2756a1327323580324f314e3b1`.

## Explicit serial authority

Both profiles explicitly enable `RISC_NATIVE_SERIAL_FILES=1` and
`RISC_NATIVE_SERIAL_APPDATA_FILES=1`. Writable namespace 2 is a separate
Runtime-owned session rooted only at `/appdata/.serial-files`. It is unrelated
to application AppData id 2 and does not reuse application grants.

TWatch does not select SD or inherit any other product's provider choice.

Neither product enables a boot-store export. No serial write reaches the active
paired boot bank. The private provider reopens bounded I/O under the existing
AppData mount/resource custody; it does not mount, format or change partition
identity. Capacity/contention may leave the optional namespace unavailable.
An uncertain close/sync retains custody and fences teardown rather than claiming
cleanup succeeded.

Use the exact pinned Runtime's `scripts/serial_files.py`,
`docs/SERIAL_FILES.md` and `docs/NATIVE_SERIAL_STORAGE.md`. The RTEF1 protocol
supports individual binary/empty files, directories, exclusive create and explicit
in-place replacement. Replacement is not atomic; interruption or abort can leave
a partial file. The connection must be owner-trusted; no authentication or
encryption is provided. No port discovery, device access or flashing is implied.

## Preservation and qualification

The frozen alarm-sleep factory remains the input baseline. Only `default.elf`,
`default.json`, `boot.json` and `cohort.json` change in its installed store.
All unrelated applications, provider ELFs, board data and alarm-service bytes
remain byte-identical. Existing native qualification also checks every profile
flag in actual compile commands. The serial gate additionally checks exact
compiled Runtime source digests, linked implementations and the private root.
Full normal/sanitized production-loader admission and independent factory
extraction remain required. These are software checks, not hardware qualification.

The previous 1.1.42 pins, native profile and qualification narrative are archived unchanged
under `history/1.1.42/` and hash-guarded. Its receipts apply only to that release.
The historical alarm-sleep and native-IDF61 contracts remain frozen by hash.

The factory image erases saved data. Back up first. No data-preserving update kit
is supplied, and standalone firmware/store assets must not be flashed independently.
