# T-Watch 1.1.37 native SDR rendering

The exact official 1.1.36 release is the predecessor. The complete 121-file, 59-ELF store is bound by individual hashes and the published 16 MiB factory SHA-256. Provisioning version 1.1.34 remains reserved.

Only waterfall.elf, its manifest version (0.3.6 to 0.3.7), and cohort.json may change. Every other store byte, including repaired shared apps, native-resolution Springboard, Home, brightness/controls, board metadata, boot grants and drivers, is preserved. The T-Watch selector does not gain Wave's atomic-storage capability.

The full 18-app set must reproduce from its immutable per-artifact source closure. Seventeen replayed ELFs must equal the published predecessor bytes. The changed RF Spectrum/Waterfall ELF uses native canvas resolution and keeps plot status text unobscured. Source replay does not authorize replacing unrelated apps or bumping their versions.

Runtime remains 4107eaeedd8c801eeaf7deb1c7bc4a943cd27342. The official 1.1.36 native ELF and BIN are reused byte-for-byte from checksum-bound published evidence, with original product provenance 9974c6ac0c6edd3a9860f18e22bcea54d10d957a. The new producer verifies the unchanged product profiles, regenerates BIN from the admitted ELF, checks native composition and complete-store admission in normal/sanitized modes, and runs 272 both-bank preserving-update cases. It never labels a newly compiled native artifact as the old build.

The preserving-update kit requires a fresh full readback of exact official 1.1.36, writes the inactive firmware/store/bank-state pair, and selects it last after readback checks. The separately labeled factory image erases saved data. Physical hardware has not been accessed or tested. Target is the non-Plus T-Watch-S3 with BMA423; radio and antenna variant need confirmation.

The narrow source-owned Actions workflow verifies all immutable pins and tests before creating a new prerelease, then downloads every published asset and rechecks its hash. Public release prose contains only the changes; release.json and UPDATE-INSTRUCTIONS.txt carry installation and hardware facts.

The focused native canvas gate requires 574 assertions and the primitive-raster gate 632 comparisons, normal and ASan/UBSan. The wider source qualification is explicitly partial: generic scenes pass 102/108 and the T-Watch profile passes 240/242. Remaining assertions reproduce on the predecessor; paired predecessor runs are normal, not sanitized. Full classification and original source evidence are included in source-renderer-qualification.json and the release evidence archive.
