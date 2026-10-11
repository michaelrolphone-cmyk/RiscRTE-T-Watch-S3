# Watch 1.1.0 touch and Buttons successor checkpoint

This is a blocked source/component checkpoint, **not a qualified full BIN**.
The [continuation report](continuation/PROGRESS.md) supersedes the earlier host
test blockers below; baseline custody and full-image admission remain blocked.
The Library baseline resolved, but its supported transfer failed on this Mac
twice. No ZIP bytes, original manifests, native ELF, store inventory or source
receipt were recovered here. The 25 policies / 27 providers / 51 ELFs are
confirmed by PR63's source and metadata, not independently read from that ZIP.

## Source selection

Start with Watch PR63 `42b2d8bfae5f7170fb0019dc5a7646f9ed4cba0a`.
Merge touch PR62 `56114a3c3b06041a9283fb6feac47099896ca5a8` on an isolated
continuation. The accepted current 0.2.1 lane remains unchanged; only this
successor's staging recipe explicitly selects `drivers/candidates/twatch_touch_022`.

Use the canvas pins unchanged:

- Utilities `814502e51125d799a7ca625b78707753ca12d4e5`; this already contains
  Buttons fix `e620160c48c11fb074378cd31a20ff8362a9659b` as an ancestor.
  Buttons source manifest is 0.1.22; Touchpad remains 0.1.14.
- System `63532e4611749acad2060d0437a883b7c4ac8fd5` for the delivered canvas
  adapter; do not substitute the newer X4 adapter.
- Runtime `e96f2affc691b929e89b624a998f0687a2746fd6`, version 0.2.4.
- Scene System pin remains `d0998415c742878b604462ce8277984c1889bc96`.

The fresh Buttons target uses the existing Contexts builder's source list and
defines, including low battery, BLE battery broadcasting, radio session,
foreground BLE, alarms, sleep, motion wake, Quick Actions/radios and Contexts.
Clock source, hardware configuration and every other application/provider are
unchanged. Preservation of their delivered bytes must still be proven by staging.

## Build components

Use Python with pyelftools and official Xtensa ESP32-S3 GCC 8.4.0
(`esp-2021r2-patch5`). All target compilation is serial. Set absolute checkout
paths W, U, S, R and READER and the compiler path CC_XTENSA; output folders
must not exist. READER supplies the existing relocation validators and its
source identity must be retained in final custody.

```sh
python3 "$W/scripts/build_touch_candidate.py" --cc "$CC_XTENSA" \
  --reader "$READER" --output "$OUT/touch"
python3 "$W/scripts/build_canvas_buttons.py" --cc "$CC_XTENSA" \
  --system "$S" --utilities "$U" --runtime "$R" --output "$OUT/buttons"
```

Fresh outputs here:

| Component | Bytes | SHA-256 |
| --- | ---: | --- |
| Touch 0.2.2 | 13,240 | `28513252f3dc6c9077bdb028ef597412d7e7951c947618ed3ddf354025028368` |
| Buttons 0.1.22 | 113,900 | `8868f53d2572feafc472eedc96f931c5c8e1f1afc1d4220717ba11ae129fe002` |

Touch matches the published candidate target exactly; 74 relative pointers
validate. Buttons passes native ELF structural validation before and after
compaction and the existing allowed-import/export checks. These do not prove
admission against the missing delivered native firmware.

## Stage only after baseline recovery

Recover and independently verify the requested Library ZIP. Retain its hash,
full 16 MiB BIN hash, build custody, native ELF and exact extracted store.
The baseline receipt consumed below must carry `version: "1.1.0"` and the
verified `store_files` SHA-256 mapping. Do not fabricate a receipt from an
unverified directory to bypass this gate.

```sh
python3 "$W/scripts/stage_canvas_touch_buttons.py" \
  --baseline "$BASELINE_STORE" --baseline-receipt "$BASELINE_RECEIPT" \
  --touch "$OUT/touch" --buttons "$OUT/buttons" --output "$OUT/stage"
```

This recipe requires the reported starting versions, 25 policies, 27 providers,
51 ELFs, both Clock 0.11.2 manifests and Model Viewer/Lists/Contexts. It changes
only the existing touch ELF/manifest and Buttons ELF/manifest, discovers the
actual touch directory from boot.json, preserves authority and checks every
other store byte. Touchpad is retained at its delivered version. It emits no BIN.

## Qualification and remaining gates

Fresh software results are recorded in checkpoint.json and adjacent logs:

- 25 production Buttons queued-contact/security cases pass normally and under
  UBSan using the candidate physical-provider source and a declared HID double.
- 44 touch contract/order executions pass with nominal/alternate wiring,
  normally and under UBSan. These use diagnostic System `8a758629...`, whose
  reducer supplies the newer test interface. This is **not** canvas adapter
  qualification. The exact canvas header rejects that newer harness.
- HID model, gesture, Touchpad and Buttons app tests pass normally and under
  UBSan, including secure pairing, interrupts, close retries and navigation.
  The later screenshot phase fails a Clang unused-function diagnostic.
- Four local sleep lifecycle modes, Hybrid policy and PMU cold-boot/rollback
  tests pass under UBSan on the selected Watch source.
- The pinned Runtime's journal, native serial adapter, USB sleep recovery and
  hash-verified Arduino 2.0.17 HWCDC tests pass normally. The Mac C++ wrapper
  suppresses only Clang's aggregate missing-braces warning; upstream remains
  unchanged. The CPU light-sleep runner remains blocked by Clang warnings after
  adapting the old Bash empty-array incompatibility.
- ASan test startup stalled, including an unsandboxed retry; this task's
  processes were terminated. No ASan pass is claimed. Host wrappers remove the
  unsupported Mac `-no-pie`; HOST_UBSAN_ONLY explicitly replaces address+undefined
  with undefined. Historical runner JSON still labels these runs sanitized;
  this document and checkpoint identify the actual UBSan-only instrumentation.

Do not emit a successor BIN yet. Still required: exact-cohort Clock low-battery
and alarm feature qualification (sleep-policy/header equality guards currently
fail), the complete adapter/pairing/cleanup path (newer harness needs a newer
Alarm header and PaperPresentation), fresh NimBLE/HCI report+boot protocol proof,
CPU Light/serial qualification, baseline/native source binding, all 51 ELF
admissions, complete graph/grant/namespace admission normally and sanitized,
deterministic SPIFFS plus independent readback and paired hash/CRC verification.

After these pass, use the pinned Utilities `scripts/package_canvas_cohort.py`
with the verified baseline, unchanged native firmware/native ELF, exact source
and compiled-input receipts, the new stage receipt and qualifications. Its
changed-path allowlist must consist of the four component paths plus cohort.json;
all remaining flash regions and app/provider bytes must remain identical. Name
any eventual output as a full initial image at 0x0; it overwrites internal data
and is not a preserving update. No physical hardware qualification, flash,
master merge, production release or full-image acceptance has occurred.
