# Watch packing recheck, 2026-10-13

This is audit evidence only. It does not change any selected product input or
partition, produce firmware, or approve a layout change.

The exact older 119-file Home/UI/catalog selection requires 19,541 live pages,
or 1,303 blocks. The current store has 1,296 blocks and requires two free blocks,
so the existing measured deficit remains nine blocks.

The pinned ESP-IDF direct-page generator has no deleted-page inflation. The
independent SPIFFS C harness writes in 8,192-byte chunks; it adds 694 deleted
pages for the same complete selection. Hypothetical 0x550000 measurement images
were independently decoded and removed after the experiment. They are not a
selected layout. All 52 preserved old ELFs already match loader-metadata-v3
fixed-point probes, with no additional demonstrated metadata savings.

The archived Python runner records the original workspace paths; replay needs
those exact source/artifact inputs, whose hashes are recorded. The C harness is
standalone against the specified SPIFFS source/config and accepts explicit
geometry, input directory, file list and temporary output arguments. No product
source is modified by either audit. Original source and evidence bytes are
preserved with their hashes rather than rewritten after testing.

The newer Contexts and full-scene components are outside this older capacity
measurement. Their qualified public source chain is recorded separately; final
composition must remeasure its exact selection and pass native/store admission.
