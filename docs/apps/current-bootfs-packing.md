# Current boot-store construction

The ABI2 full-image builder uses the unmodified ESP-IDF v4.4.7 `spiffsgen.py`
from commit `38eeba213aa695aabfd6d89aa9f5078dbe5a94c3`. Source and Apache-2.0
license hashes are in `licenses/spiffsgen/SOURCES.json`. Historical ABI1
builders retain their existing mkspiffs construction path.

PR31's first hosted assembly failed with mkspiffs `SPIFFS_write error(-10001)`
while incrementally writing the complete store. The same 72 payloads packed
locally, so that failure did not establish that the logical payload exceeded
the partition. The official generator constructs the final pages directly,
avoiding the incremental writer's allocation and garbage-collection overhead.
It is called in sorted path order with zero metadata for deterministic output.

The wrapper accepts only canonical ASCII relative member names, including the
leading slash and NUL in the 32-byte name limit. These are build-owned app and
provider paths, not user filenames. Rejecting non-ASCII paths avoids the pinned
upstream generator's character-versus-byte name-padding limitation.

The image remains exactly `0x510000` bytes. Page size 256, block size 4096,
name length 32, metadata length 4, little endian, magic and magic-length flags
match the pinned ESP32-S3 SDK. Every image is independently decoded and compared
to every input byte, then mounted/unpacked by the existing pinned mkspiffs
reader. The final full BIN is decoded again and receives the existing actual
Runtime/ELF execution checks. Capacity exhaustion or fewer than two whole free
blocks fails construction; no partial output is published.

The build manifest records exact generator/configuration/image hashes and
payload/occupied/empty-block counts. The 72-file delivered cohort contains
3,845,523 payload bytes and constructs into 1,037 occupied blocks with 259 empty
blocks. This is offline image capacity evidence, not physical write endurance,
garbage-collection latency, or on-device qualification. Installed boot files are
read-only; writable app data uses the separate LittleFS partition.

References:

- [Pinned official generator](https://github.com/espressif/esp-idf/blob/38eeba213aa695aabfd6d89aa9f5078dbe5a94c3/components/spiffs/spiffsgen.py)
- [ESP-IDF SPIFFS image tooling and filesystem limits](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32s3/api-reference/storage/spiffs.html)
