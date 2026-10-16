# T-Watch 1.1.38 native Home faces

This immutable successor begins with the exact published native-SDR 1.1.37
factory and evidence ZIP. It replaces only `default.elf`, changes the existing
Home manifest version to 0.16.0, and changes the product cohort version/source.
All existing capability requirements, grants, providers, boot policy, SDR,
Springboard, native firmware, partition geometry, and the other 118 store files
remain unchanged.

The source-owned qualification checks out immutable shared Watch, System and
Utilities commits in isolated directories, builds the synchronous-NVS Home
twice with the pinned GCC 8.4.0 compiler, and requires both ELF digests to match.
It runs the shared native face, effect, layout, viewport, lifecycle, retained
wake, gesture and quick-action tests, including their sanitizer variants.
Both packed atlas decoders are checked exhaustively against original bytes,
malformed codec blocks, and 1,632 original-versus-packed native frame hashes.

Every installed ELF is admitted by the real Runtime loader in normal and
ASan/UBSan modes with no hardware or storage calls. A mutation suite rejects
out-of-scope payload, manifest, cohort and native changes. All 272 preserving
update cases cover either active bank, selector sectors, interruption/torn
writes, readback corruption and unsafe baselines. Packaging independently
repeats that fault model and checks native ELF-to-BIN reproducibility.

The factory image erases saved data. The preserving kit requires a fresh full
device readback of the exact 1.1.37 predecessor and writes the inactive pair
before a separately verified final OTA selector. Host proofs do not establish
physical-device behavior or authorize device access.

The release workflow builds from the tagged source and never overwrites a tag
or existing assets. Publication is gated by `publication_enabled` in the source
pins and by successful qualification, followed by re-download/hash checks.
