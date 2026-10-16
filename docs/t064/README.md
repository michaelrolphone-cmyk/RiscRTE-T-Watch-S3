# T064 durable crash reports — watch

Cumulative 1.1.33 from exact 1.1.32. Native firmware, partitions, loading interstitial and stage logs are preserved. Only Home, its manifest, cohort metadata and (RGB only) explicit crash grants change. X4 SD contents are unchanged from .120.

The healthy default Home copies retained crash sequence and stack evidence at next boot. The same logical report text is presented and atomically backed up before acknowledgement. Every report page must finish and the user must Continue. Unavailable internal storage leaves native evidence pending. A full eight-report queue never evicts reports. SD export retries after 30 seconds, defers absent/USB-exported media, verifies the exact final file before removing its internal copy, and stops after uncertain custody.

AppData namespace 61; physical LittleFS path `/appdata/n0000003d/crash-spool.bin`. The internal path is not an automatically exposed USB drive. Retrieve it through a qualified filesystem/readback workflow and run shared System `scripts/extract_crash_spool.py` to validate CRC and extract exact `.txt` reports. SD-capable products export to `/CrashReports/<firmware-sha256>-<boot8>-<sequence8>-<text-crc8>.txt`. Watch has no SD volume and keeps its reports internally.

RGB Home uses namespace 61 because namespace 62 belongs to Lists. Waveshare selects SD instance 12; X4 retains instance 9 and its existing namespace 62. T-Watch selects no SD. RGB uses `WATCH_CRASH_REPORT`; X4 uses `PORTABLE_CRASH_REPORT_SD`. Wave keeps atomic preferences and Watch keeps NVS preferences. Lossless font packing preserves all rendered pixels and provides module-store headroom.

Build from the workspace using the checked-in assemble/verify scripts and the exact baseline full image named in source-pins. Shared RGB: `scripts/build.py --role default --preferences nvs`; Wave additionally selects `--crash-volume 12`. X4 target recipe is the existing full-profile recovery-107 build, selected by `.github/workflows/t064-crash.yml`, with exact deployed baseline reproduction and a repeated candidate build. No hardware flash or hardware qualification is claimed.
