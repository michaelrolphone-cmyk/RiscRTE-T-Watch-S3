# TWatch 1.1.33 cumulative T064 test

Use the preserving-update kit only from exact 1.1.32. Follow its README: take a fresh complete readback, verify staged writes, and write selection LAST. Do not bypass planner refusal.

The separate `factory-erases-data-0x0.bin` is a full 16 MiB factory image and overwrites saved data.

Existing native firmware, partition layout and every non-Home application are byte-preserved. X4 keeps the existing cumulative .120 SD package, including GameBoy and OBDTest; no T064 SD replacement is needed.

Reports are saved in the internal AppData spool `/appdata/n0000003d/crash-spool.bin`. This path is not automatically exposed through USB. A qualified filesystem readback/extraction is required for internal retrieval; use the included `extract_crash_spool.py` on the recovered spool. T-Watch retains reports internally; this profile has no SD volume.

The queue holds eight reports. A full queue preserves existing entries and leaves new native evidence unacknowledged. The report is acknowledged only after every page was presented and its exact text was durably saved. This does not promise unlimited history or survival of RTC evidence across loss of power before durable capture.

Normal and ASan/UBSan spool, archive, session, renderer and actual paginated Home tests passed. RGB pixel/native-height regressions passed across 362 golden frames. Full source-bound Runtime admission passed for 43 X4, 62 Waveshare and 59 T-Watch ELFs, with exact-baseline preserving-update fault tests. X4 target CI reproduced the deployed baseline and two identical candidate builds. No hardware qualification is claimed.

Factory SHA-256: `077676642f2a3e938cf6fea497e6322dad198e1c2e98236d9367fb6bb5dcefca`
