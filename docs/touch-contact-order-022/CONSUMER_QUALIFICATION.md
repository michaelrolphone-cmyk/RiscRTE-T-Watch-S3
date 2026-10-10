# Watch FT6336U 0.2.2 consumer qualification

Candidate provider SHA-256: `abeaf6783c61f1adc3eab0448077d4453fc057233b0746bb3dfc169fcbdb517f`.
Baseline 0.2.1 SHA-256: `01b5247d473f3bc7ce34a6de79d259854902637bf78547ce3cbe53a4e407fbc6`.
No provider implementation, product recipes, hardware, releases, or merges were changed by this qualification.

## Results

- 25 exact existing Buttons queue/security/release cases passed normally and under ASan/UBSan.
- 96 actual FT6336U + shared Runtime/ProviderGraph + production scene cases passed normally and under ASan/UBSan. Both modes produce identical outputs: 20,808 contacts per mode; 60/80/133/200 ms press periods; alternating, repeated and two-finger overlapping keys; keyboard and ordinary-scene Back/Home; 1/17/2300 ms panel completion; zero/500 ns modeled per-pixel CPU cost. Assertions require exact key order/count, no action before release, action within 20 ms of modeled release, balanced provider lifetime and clean display custody. Maximum modeled capture interval was 3,000 us.
- 50 production Touchpad/Buttons app and adapter cases per mode passed for both baseline and candidate, normally and ASan/UBSan. The 692 compressed frame files (346 per mode), their pixel content, and action/cleanup/Runtime-logger replay logs are identical between versions. Tests retain all original scenario assertions for taps, tap-drag, X/Y/free scrolling, two-finger right tap, key reports, pairing acceptance/rejection/movement/multitouch/gap recovery, reconnect, disconnect, low battery, sleep, alarms, raw gaps, Back, quick controls, cleanup failure retries, navigation Home, nested edits, cancel/save and retry.
- The full production app/adapter regression demonstrates the original defect beyond the reducer: an existing top-edge contact moves into the panel-open threshold in the same coherent FT6336U report that adds a second contact. Dispatch is delayed by 1 ms after capture. Baseline 0.2.1 makes Quick Controls visible; candidate 0.2.2 never does. Both production apps pass this negative/positive control normally and ASan/UBSan (four processes per version). Only fixture transport/time is changed; the production adapter and Quick Controls implementation are included unchanged, with a read-only observation accessor.
- Real production NimBLE + independent HCI central sees exact key press and neutral ATT packets, twice each in report and boot protocols, with no later watchdog duplicate. Repeated with the FT6336U/app seam under ASan/UBSan. The reused NimBLE binary itself is not newly sanitized in this run.

## Fixtures and limits

The Runtime harness is adapted from the existing GT911 Runtime runner, but links the actual FT6336U source and strict Watch 13-byte register/I2C/GPIO fixture. It uses Watch 240×240 RGB565 geometry and the non-paper profile. The independently sampled physical model holds the latest contact state every 5 ms; there is no GT911 READY/ACK latch. None of the GT911 results are counted as Watch evidence.

The renderer fixture only changes the old positional Runtime API initializer to a designated initializer so newer SDK members are zeroed without suppressing compiler diagnostics. Its generic `raw-home` case attempts a primary hardware button in a touch report: FT6336U exposes no such button in either version, so that impossible injection is excluded. Actual navigation Home and all touch controls remain tested. These app renderer comparisons use their original synchronous display fixture; the fast/slow/busy display and CPU-load matrix is the separate Runtime keyboard/scene harness.

All evidence is software-only. GPIO, I2C, controller scans, HCI central and display are modeled. There is no measured device latency, radio/hardware test, rebuilt selected Watch product, flash, merge or release claim. Shared Runtime is local commit `0f17a435f99d02d60ca50df1d1a51fcef123db89` (parent-supplied public exact-tree equivalent `b25b1d467a557e8d693211cff2eff959eb9c79de`). `qualification.json` records exact actual checkout commits and source hashes.

## Reproduction

Paths below point to the verified source checkouts used here. Each output directory must be new for the Buttons runner.

```sh
Q=/workspace/shared/watch-contact-order-qualification
U=/workspace/shared/ble-buttons-report-recovery-20261010/utilities
D=/workspace/shared/ble-buttons-report-recovery-20261010/drivers
S=/workspace/shared/ui-qualified-raster-source-20261010/system
W=/workspace/shared/watch-touch-contact-order-022
R=/workspace/shared/x4-wifi-ui-plan-057/runtime-source
C=drivers/candidates/twatch_touch_022/driver.c

python3 "$U/scripts/test_hid_buttons_watch_queue.py" --system-apps "$S" --watch "$W" --touch-source "$C" --output "$Q/replay-buttons"
python3 "$U/scripts/test_hid_buttons_watch_queue.py" --system-apps "$S" --watch "$W" --touch-source "$C" --sanitize --output "$Q/replay-buttons-san"
python3 "$Q/scripts/test_watch_runtime.py" --runtime "$R" --watch "$W" --utilities "$U" --scene "$S" --output "$Q/replay-runtime"
python3 "$Q/scripts/test_watch_runtime.py" --runtime "$R" --watch "$W" --utilities "$U" --scene "$S" --sanitize --output "$Q/replay-runtime-san"
python3 "$Q/scripts/test_hid_renderer_isolated.py" --utilities "$U" --output "$Q/replay-renderer" --system-apps "$S" --watch "$W" --watch-touch-source "$C" --runtime "$R" --low-battery
python3 "$Q/scripts/test_hid_renderer_isolated.py" --utilities "$U" --output "$Q/replay-renderer-baseline" --system-apps "$S" --watch "$W" --watch-touch-source drivers/current/twatch_touch/driver.c --runtime "$R" --low-battery
python3 "$Q/scripts/test_watch_second_contact_app.py" --utilities "$U" --output "$Q/replay-second-contact" --system-apps "$S" --watch "$W" --watch-touch-source "$C" --runtime "$R"
HID_RENDER_EXPECT_UNSAFE=1 python3 "$Q/scripts/test_watch_second_contact_app.py" --utilities "$U" --output "$Q/replay-second-contact-baseline" --system-apps "$S" --watch "$W" --watch-touch-source drivers/current/twatch_touch/driver.c --runtime "$R"
python3 "$U/scripts/test_hid_buttons_watch_queue.py" --system-apps "$S" --watch "$W" --touch-source "$C" --seam --output "$Q/replay-seam"
python3 "$U/scripts/test_hid_buttons_wire.py" --drivers "$D" --provider "$D/build/ble-hid-host/driver.so" --app-seam "$Q/replay-seam/app-seam.so" --output "$Q/replay-report.json"
python3 "$U/scripts/test_hid_buttons_wire.py" --drivers "$D" --provider "$D/build/ble-hid-host/driver.so" --app-seam "$Q/replay-seam/app-seam.so" --boot-protocol --output "$Q/replay-boot.json"
```

For the sanitized wire seam, add `--sanitize` to its build, and run Python with `LD_PRELOAD=$(cc -print-file-name=libasan.so) ASAN_OPTIONS=detect_leaks=0`. Sanitized tests use address and undefined-behavior sanitizers; leak detection is disabled, as in the original runners.
