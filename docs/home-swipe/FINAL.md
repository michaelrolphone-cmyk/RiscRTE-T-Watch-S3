# Qualified Watch 1.1.20

Compiled source: `b7a6cf0d2505ecf9b1c625bbfcc6d4048c13b471`. Source CI run 38322046467 passed.

Only `WATCH-1.1.20-FULL-INITIAL-ERASES-DATA.bin` is the user deliverable: 16,777,216 bytes at offset `0x0`, SHA256 `f8195d2af2dfdcc9f2c0413883efd97f6efe4d62eb90cfd4e5cab5aec5332cb6`. A full initial image erases settings and app data.

Normal and ASan/UBSan full-cohort receipts are identical; all 55 ELFs pass admission; two free SPIFFS blocks remain. Native firmware, all other 54 ELFs, and 110 other store files are byte-identical to Watch 1.1.19.

The repair captures ordered touch observations during rasterization and replays them only after frame writes stop. RTC reconciliation corrects retained display-time divergence after the first input opportunity, preserving the fast initial frame. Ordinary unavailable RTC keeps Home alive after a fresh valid-native authority check and shows TIME CHECK ERR. Physical hardware timing and the cause/magnitude of real-device drift remain unmeasured; intermittent hardware freeze is not claimed resolved. No flashing or hardware execution occurred during qualification.
