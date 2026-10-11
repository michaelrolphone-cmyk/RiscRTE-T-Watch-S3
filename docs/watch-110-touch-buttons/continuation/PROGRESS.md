# Continuing qualification; full image remains blocked

## Authoritative baseline comparison update

The parent subsequently supplied the authoritative full BIN SHA-256
`c4827bc7f2157cc14fd041b9c617f5f716264f8c1ee28d7415b5175782d0263a`,
size 16,777,216 bytes, original member
`Watch/TWatch-S3-1.1.0-Canvas-Apps-FULL-INITIAL-ERASES-DATA.bin`.
None of the ten previously hashed local candidates matches. The staging script
now requires this exact full BIN and independently decodes all 105 store files
before comparing the extracted store and custody receipt. An equal-sized wrong
BIN is verified to fail before receipt access or output creation. Positive
staging remains unexecuted because the authentic bytes are still unavailable.
Await the confirmed ID of the parent-prepared Watch-only Library input; no
exhausted transfer route has been repeated and no substitute has been accepted.

The earlier search report below is retained as history; the authoritative hash
is no longer missing, but baseline custody remains unverified locally.

No new production source was changed. Runtime stays at
`e96f2affc691b929e89b624a998f0687a2746fd6` (0.2.4), System at
`63532e4611749acad2060d0437a883b7c4ac8fd5`, Utilities at
`814502e51125d799a7ca625b78707753ca12d4e5`. The rebuilt component hashes in
the preceding checkpoint remain unchanged. No full BIN has been produced.

## Exact Library errors and local custody search

Both previous executions returned exit code **1**, with exactly this combined
output:

```text
library file transfer failed: download failed
```

Attempt one ran inside the workspace sandbox. Attempt two was an approved
`require_escalated` execution using the same unmodified Library transfer helper.
Neither was an automatic-approval rejection. The helper emitted no HTTP status,
Python exception, SSL/DNS diagnostic or lower-level cause. No further transfer
was attempted, and no stronger explanation is supported by the available output.
Library preparation itself succeeded and resolved a 7,409,174-byte ZIP.

The requested local search covered Codex build workspaces, Downloads, Desktop
and /tmp. No named canvas/Watch 1.1.0 output or ZIP of that exact byte size was
found. Ten 16 MiB BIN paths were hashed into local-baseline-candidates.json;
their names identify other X4 builds. None was accepted or substituted. The
delegation did not include the authoritative receipt/BIN hash, which was
requested separately. Local absence alone does not authenticate another image.

## Power and serial

The canonical recipe from Watch `2681c07d626af2cdac615c8728eea405b4a032fd`
was already present unchanged at the previous checkpoint. Its original recorded
combination used System `8a758629...` and Runtime 0.2.3. Canvas's older System
header lacks newer Runtime suffixes, and its policy differs from Watch's local
policy, so the earlier equality checks correctly refused an implicit mixture.

The explicit diagnostic extension now stages the **selected Runtime 0.2.4**
headers, the existing Utilities Alarm sleep suffix, and the named System
`8a758629...` sleep-policy header before suppressing the duplicate local guard.
Ten actual Clock/local-sleep programs pass normally and under UBSan: alarm and
low-battery variants, low-battery crossings, manual overrides, reboot,
charging/unknown status and configured Hybrid timer. Sources, staged header
hashes, commands and policy selection are in power-canonical.json. This is an
explicit diagnostic binding, not a claim that the missing delivered Clock ELF
was built with that policy or that its bytes match this source closure.

```sh
python3 "$W/scripts/test_selected_power_union.py" \
  --system "$S" --runtime "$R" --alarm-source "$U" \
  --policy-source "$SYSTEM_8A758629" --canonical-runtime-sdk \
  --sanitizers undefined --output "$OUT/power-canonical"
```

The exact pinned Runtime CPU Light tests also pass: repeated wake,
owner/input/stale/foreign-token rejection, active wake, held SPI/reentrant I2C,
arm/entry failure, retained cleanup, deferred USB recovery and SPI lifecycle.
The generated Mac runner only replaces an empty Bash array with an already-used
compiler-warning option (old macOS Bash otherwise fails under `set -u`). The
C++ wrapper suppresses Clang diagnostics for aggregate braces, unused private
fields and an unused-but-set diagnostic counter; production Runtime source is
unchanged. The existing journal, serial adapter and hash-pinned Arduino 2.0.17
HWCDC checks remain passing. No device sleep current or USB-host enumeration
was measured.

## Canvas Buttons adapter

`test_hid_renderer_isolated.py --canvas-buttons` now uses exactly the target
builder's feature definitions and validates the canvas source pins. The fixture
uses the correct legacy Alarm v1 table and explicitly declared OFF Contexts and
telemetry doubles to satisfy the selected background clients. These doubles do
not qualify real Contexts capture or battery broadcasting.

The first complete run passed 42/48 executions. Quick Controls, Home and
edit-Home failed normally and under UBSan, and the same failures reproduced
with the 0.2.1 provider. Their logs are retained unchanged. Inspection found:

- Contexts shifts the radio tiles up by 30 pixels. The old scenario clicked
  the handle rather than both radio controls. The corrected scenario clicks
  actual Wi-Fi/Bluetooth tiles and retains the original radio/cleanup assertions.
- The canvas adapter's `input_navigation_take` explicitly maps only
  Back/Confirm/arrows. Synthetic Home is not a supported mapping in this source
  profile. Home and edit-Home are recorded as unsupported, not passed, and are
  excluded from the corrected supported-profile matrix.

The corrected matrix passes **44/44**, normal and UBSan: pairing acceptance,
rejection, moved/multitouch/gap recovery, reconnect/disconnect, queued keys,
low battery, sleep, alarms, Back, Quick radio controls, cleanup retries,
nested edits and cancel/save/retry. It links the actual FT6336U candidate,
Buttons application, canvas adapter and pinned Runtime serial logger. Only
peripheral/background services are host doubles; local sleep itself is tested
separately above. No assertion was weakened to obtain this result.

```sh
HID_SANITIZERS=undefined python3 "$W/scripts/test_hid_renderer_isolated.py" \
  --utilities "$U" --system-apps "$S" --watch "$W" --runtime "$R" \
  --watch-touch-source drivers/candidates/twatch_touch_022/driver.c \
  --canvas-buttons --keep-going --low-battery --output "$OUT/canvas"
```

## Real NimBLE wire replay

Fetched exact Drivers `4088b6892c2e2654b0342f04a7d191068e4a8e2e`, whose
manifest is BLE HID 0.1.2 as selected by the Watch runtime-features source
profile. Vendored-source checks pass; production sources are unchanged. The
host linker wrapper translates only ELF linker options into Mac dylib options.

The independent central performs Secure Connections numeric comparison,
ECDH/CMAC validation, persisted bonding, service/characteristic/descriptor
discovery and encrypted CCC setup. Actual FT6336U plus production Buttons
delivers two exact press/neutral transactions in both report and boot protocols,
with no later watchdog duplicate. All four runs pass: normal seam/report,
normal seam/boot, UBSan seam/report, UBSan seam/boot. The NimBLE dylib is a fresh
normal build; it is not claimed to be sanitized. Receipts retain all binary
and oracle/seam hashes.

## Remaining gates

A minimal puts-only ASan program times out after eight seconds without output,
independently of Watch code. ASan remains a host-startup blocker; no ASan result
is claimed. The wrappers and actual UBSan selection are preserved here.

Still required: authenticated baseline/receipt and original native ELF,
verification of the exact delivered Clock/source closure, execution of the
four-path preservation stage, all 51 target ELF and complete graph admission,
appropriate sanitizer qualification, and deterministic full-image assembly,
independent readback and paired hash/CRC checks. The task is **not complete**.
There has been no master merge, hardware flash or accepted firmware release.
