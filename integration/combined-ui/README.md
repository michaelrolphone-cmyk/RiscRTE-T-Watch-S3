# Combined UI and Spectrum test firmware

Waveshare 0.1.25 / T-Watch S3 1.1.26. Includes capability-sized high-resolution Nova launcher, complete app icons, Files metadata, hidden helper entries, one-time cold-boot intro, fast later/deep wake and production Waveshare panel startup without diagnostic color flashes. The published Spectrum lifecycle and explicit namespace corrections remain byte-identical.

Source pins are in sources.json. Home uses its locked System/Utilities dependencies and shared scripts/build.py --role both. Springboard uses System Apps at the recorded revision, full Contexts, native custody and checked storage, with GCC 8.4 -Os -flto -flto-partition=one -Wl,-u,__divsf3; its exact command and compaction proof accompany the release. Shared Home adds lossless calendar atlas compression to fit the fixed store; no app or feature is removed.

Build native Runtime single-job with watch-expanded-profile.ini (Watch) or the included native/expanded-candidate.ini (Waveshare), overlaying the product native/VendorDisplay.cpp and pinned WaveshareVendorGfx library as in the existing vendor build. Run scripts/build_combined_ui.py with the checksum-pinned prior Spectrum factory BIN, native runtime checkout, shared Home output, launcher ELF, Watch product checkout for current_bootfs, output directory, product name and this product commit. It verifies native source identity, unchanged partition table, deterministic bootfs round trip and preserved Spectrum/provider bytes.

Factory image at offset 0x0 erases saved data. No hardware flashing or qualification is claimed. The SD LoRa payload remains unchanged and compatible.
