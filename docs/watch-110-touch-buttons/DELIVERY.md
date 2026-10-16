# Watch 1.1.1 software-qualified successor

Full initial BIN: `TWatch-S3-1.1.1-Canvas-Apps-FULL-INITIAL-ERASES-DATA.bin`,
16,777,216 bytes, SHA-256
`799eb39937a380ac5d11eb5eaf1eaf0e8416edddd2ad5fa8e02030db6785f356`.
It overwrites internal settings/AppData if flashed at 0x0. No device was flashed,
no branch was merged, and no physical or preserving-update qualification is claimed.

The Watch-only Library input `libfile_18a0d7ed70548191bc0df13b5351a71f`
materialized successfully with the current unmodified helper and configured Python.
ZIP SHA-256 is `387064773f032955a71e528b75442cb9f70d6c6b0f27b972011f305dd7816dbd`.
The full baseline BIN matches `c4827bc7f2157cc14fd041b9c617f5f716264f8c1ee28d7415b5175782d0263a`.
All 105 files independently decoded from that BIN match extracted files and custody.

## Changes and preservation

Touch 0.2.1 becomes 0.2.2 from PR62/56114a3c. Buttons 0.1.14 becomes 0.1.22
from Utilities e620160c, already contained in the canvas Utilities tree 814502e5.
Only their four ELF/manifest paths plus cohort metadata change. The other 100
store files are byte-identical: Model Viewer, Lists, temporal Contexts, Touchpad
0.1.14, all radio/BLE providers, battery broadcasting and Clock remain preserved.

Actual Clock is `default.elf` 0.11.2. `clock.elf` is a distinct return launcher
0.11.0. Clock and Springboard both reproduce byte-for-byte from the public source
trees. All 98 recorded Clock source dependencies match; the generated Springboard
catalogue is validated by the identical final ELF. No newer diagnostic policy is
substituted in these artifacts.

Native Runtime is rebuilt from public e96f2aff, the exact tree corresponding to
the baseline's original local dd46f533 commit. The original native ELF was absent
and is not represented as recovered. New firmware is 1,332,928 bytes, SHA-256
`8ff4a6f244f267724e5002feb1f202833b036a094621cc2b79a78671a6277194`.
New ELF is 21,782,668 bytes, SHA-256
`07041d48dd2c6a9fe6e7cea775e44b3ba71837adb20d24c7624b0516dbbd7cfc`.
Both are delivered. Runtime remains 0.2.4 with policy/requirement rows24, radio IQ,
paired banks and AppData. Bootloader and partitions reproduce exactly. Native
exports, TLS certificate bundle, rollback hooks and IQ reservation are proven
against this new ELF/BIN pair; native firmware bytes are explicitly changed.

Live checks still identify Watch PR63 at 42b2d8bf and touch PR62 at 56114a3c.
Runtime and System selected heads remain unchanged. Utilities advanced to
f43241c2 with a Hollow Trail/Canvas letterbox change; Buttons source is unchanged.
The Watch's actual composition still pins 814502e5, which is retained.

## Qualification and limits

- 51/51 target ELFs pass strict native ABI/loader admission. Complete 25-app,
  27-provider graph passes normal and UBSan admission, with zero hardware/storage
  calls. This admits target bytes; it does not execute Xtensa instructions on Mac.
- Actual touch + Buttons + canvas adapter: 44/44 supported scenarios pass normal
  and UBSan. Queued taps, pairing accept/reject, cancellation, cleanup retries,
  low battery, alarms, sleep, Back and radio controls are covered. Synthetic Home
  is unsupported by this adapter and is excluded, not counted as passing.
- Actual NimBLE wire replay passes report/boot protocol, normal and UBSan app
  seam, including numeric pairing, persisted bonding and two exact press/neutral
  transactions without duplicate watchdog delivery. NimBLE itself is unsanitized.
- Delivered-source Clock low-battery tests pass normally and with UBSan, retaining
  the actual distinct local/shared policy headers and include order. Four local
  sleep lifecycle configurations pass UBSan with the selected System headers.
  The separate newer-policy diagnostic suite is not used as delivery proof.
- Exact Runtime CPU Light, retained cleanup, SPI/I2C lifecycle, serial journal,
  USB recovery and hash-pinned Arduino HWCDC host checks pass. Physical sleep
  current, radio operation, USB host enumeration and battery broadcasts are
  not measured. Peripheral/background doubles do not qualify live Contexts.
- Deterministic SPIFFS, independent mkspiffs readback, paired SHA/CRC and unchanged
  flash-region comparisons pass. AddressSanitizer cannot start even a minimal
  program on this host; only normal/UBSan qualification is claimed.

`delivery/build-custody.json` is the generated admission/assembly receipt;
`delivery/package-spec.json` contains exact sources, artifacts, hashes and paths.
Its `host_sanitizers: undefined` and the recorded compiler wrappers make the
receipt's `sanitized: true` cohort result explicitly UBSan, never ASan.

## Reproduction

Use the checkout locations from package-spec.json, or relocate every absolute
path consistently and regenerate artifact hashes. Python needs pyelftools and
PlatformIO; esptool also needs intelhex (installed here in workspace-only
`.host-python-deps`). Use the pinned Xtensa 8.4.0 esp-2021r2-patch5 toolchain.

1. Build touch and Buttons with the preceding RECIPE.md and exact public pins.
2. Run `scripts/stage_canvas_touch_buttons.py` against the authenticated baseline
   store, full BIN and custody, plus the two component build directories. The
   stage receipt must report exactly four changed paths.
3. In pinned Runtime run `pio run -e esp32s3-16mb-appdata-iq-policy24 -j 1`.
   Supply the workspace Python dependency directory via PYTHONPATH if needed.
4. Reproduce Clock/Springboard using `scripts/build_canvas_launchers.py` with
   pinned System, Utilities, Runtime and the baseline store; compare ELF hashes.
5. Run the existing continuation tests and the delivered-source low-battery
   harness in `delivery/test_canvas_low_battery.py` from the parent workspace.
   This harness intentionally runs only Clock tests; it does not claim the newer
   alarm-resume suffix against canvas's older Alarm header. Local sleep lifecycle
   tests cover the selected legacy/current guarded paths independently.
6. Run pinned Utilities `scripts/package_canvas_cohort.py --spec SPEC --output OUT`.
   On this Mac use the recorded host compiler wrappers first in PATH and explicit
   `HOST_UBSAN_ONLY=1`. Preserve `host_sanitizers: undefined` in SPEC. On a working
   ASan host use the standard compiler and record address+undefined instead.
   Recovery tools are independently pinned to X4 dfa5ebdd; mkspiffs is hashed in
   SPEC. Do not substitute an unrelated native ELF or relabel its source identity.

The source checkpoint embedded in the new cohort is a1d785e; subsequent documentation
commits do not change any compiled production source. Accepted release metadata
is untouched. This is a development candidate with the limits above.
