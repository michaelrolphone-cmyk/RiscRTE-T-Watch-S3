# Watch 1.1.16 mounted Files test increment

Base: delivered Watch 1.1.15, product afdab33b66d18d2afc5d9da3abdbcfe90490941a, full-image SHA256 c96cc199075da214dc17fead513b73570df7a216a32f30cf8e583b6dfc2aedb1.

Files 1.5.31 source: RiscRTE-System-Apps 0accd8905b5a64bf5e9269fe92a6e47c9fd1cc90 (PR109). Rebuild with its build_watch_shared_files.py using Watch profile 089868395268b696c05651c33816345bfe0425df, Utilities fc0bdbbbc600ce891e60c44d091fce0586ade7d8, SDK Runtime 3b90cd11cf0ff4e8116bb54d2d9eb9c7c67a148b and the verified 1.1.5 baseline store. The builder records all source hashes and retained feature flags/grants.

Compose with scripts/assemble_watch_mounted_files.py and the exact delivered native 267aab6d9382ce4921a1536fab1620749b2f5301 pair. It changes only Files ELF/manifest and cohort identity. All 108 other store files, all 25 applications / 30 providers, Clock 0.11.5/wake behavior, native bytes, boot policy, provider grants, and measured boot-order packing remain intact. Full image admission validates 54 ELFs; run it normally and with SANITIZE=1, ASAN_OPTIONS=detect_leaks=0 under ptrace.

Nearby connection setup now mounts the peer in the existing file browser. Normal rows, folder navigation, preview and supported file actions replace the separate remote panel. X4 can materialize a remote file to SD and invoke its declared handler. Watch's generic non-SD handler Open remains unavailable; this test build does not invent an SD volume. Watch shares only its eight admitted saved-file paths; folders with no saved records are genuinely empty. Export creation/replacement is supported, arbitrary folder mutation is not.

Full initial 16 MiB flash at 0x0 erases internal settings, saved Wi-Fi and app data. Watch has no SD package. Deliver the plain BIN; preserve matching symbols and qualification/source receipts separately. Software qualification is not a physical pairing/performance claim.
