# Watch Scanner shared input component

This recipe changes only BLE Scanner, from the delivered Watch 1.1.17 component
0.2.17 to product-selected 0.2.18. Sensor aliases use the existing ui.text-input@1
service with plaintext capacity and the shared NOVA keyboard. The only added
Scanner policy grant is ui.text-input@1, instance 0. There is no native change.

Use build_watch_keyboard_scanner.py with the exact predecessor clients.json,
delivered store, frozen Watch profile, pinned System/Runtime and published
Utilities source. The recipe verifies inherited feature flags and Watch sources,
the original Scanner hash, every compiled input, allowed imports/exports and
Xtensa structure. It selects only the Watch-supported 240x240 color Scanner
renderer. Other Utilities profiles retain their portrait implementation.

The 148000-byte component ceiling leaves room for the bounded Watch store.
The selected adapter uses checked, capture-cooperative direct rendering; it does
not add the separate raster command replay implementation. The shared keyboard
host still owns ordered capture and presentation independently. No safety,
Contexts, radio, alarm, low-battery, quick-control or sleep feature is disabled.
The existing PORTABLE_ASYNC_RGB565 define is retained for recipe parity; the
current adapter does not use it as a renderer selector.

Run test_watch_keyboard_scanner.py against the exact target build directory and
BLE driver source. It compiles production Scanner, adapter, Watch compact scene,
text input and BLE sensor driver code. The copied hardware boundary exercises
save/cancel/reopen, crown Back, single-action Home, delayed presentation, four
ordered repeated-key edges in 12 ms with no intervening frame, and retained or
revoked custody at every modal and storage boundary. Every case runs normally
and under ASan/UBSan. LeakSanitizer is disabled for the container environment.
These are host-source tests, not execution of Xtensa instructions or hardware.

Final integration must preserve the separately qualified RTC/alarm component
pair, merge the single Scanner grant explicitly, regenerate product identity,
and run complete Runtime admission and ordered SPIFFS packing. Do not relabel
an admission-only component overlay as a released product build.
