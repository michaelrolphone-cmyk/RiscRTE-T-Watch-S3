# Watch 1.1.15 boot-order packaging test

Reorders physical SPIFFS file placement from the exact delivered 1.1.14 image. Native, all 54 app/provider ELFs, manifests, policy, resources, Points, tap/crown wake and genuine sleep failure notices remain byte-identical. Only cohort product identity and matching bank digest change. No filesystem index or device-side validation is added.

The exact-byte experiment retained all 111 file payloads and the same 25 free blocks. The real Runtime metadata trace used 41,102 flash-read calls in SPIFFS opens with the previous order and 187 with the new order. The source-derived deep first-frame closure used 44,393 versus 234 open-phase reads (total mount/open/read calls 52,806 versus 8,645). These are software replay counts, not elapsed hardware time or confirmation of deep sleep. Cold/invalid-time, timer alarm, deferred services, all-files and seeded random-order replays also pass, including ASan/UBSan with the unchanged SPIFFS packed-access alignment check excluded.

Compose from a clean published checkout:

    python scripts/assemble_watch_boot_order.py --baseline-image WATCH-1.1.14-FULL-INITIAL-ERASES-DATA.bin --runtime EXACT_RUNTIME_CHECKOUT --native VERIFIED_NATIVE_DIRECTORY --output NEW_OUTPUT

The native directory must include matching firmware.bin/.elf and crown-wake-profile.ini. The baseline image hash and source-qualified native pair are pinned in the composer. Use --compose-only to produce the image before the production admission check; its receipt explicitly marks full admission pending. Run again with --verify-only, then SANITIZE=1 ASAN_OPTIONS=detect_leaks=0 with --verify-only for final admission.

The raw 16 MiB full-initial image erases saved device data/settings when flashed. Sleep acquisition failure remains an investigation; this packaging change does not claim to fix it. Hardware first-frame timing remains to be tested.
