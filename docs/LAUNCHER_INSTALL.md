# Diagnostic variant: 0.4.0 touch direction

This branch preserves the original 0.4.0 implementation and source pins. Only
the shared Springboard, Battery and Settings ELF builds select identity touch
coordinates instead of the old 180-degree client transform described below.
Display rotation itself remains unchanged. See TOUCH_DIRECTION_VARIANT.md and
the exact 22-file custody proof. This is a configuration variant, not a release.

The historical baseline description follows; its touch-transform180 statement
is superseded by identity0 for these three shared apps only. Clock and every
physical driver are byte-identical to the original confirmed-working image.

# Optional NOVA launcher and Settings bundle

This is the optional Watch PR5 line. The accepted PR6 clock0.3.1 and its flashing
bundle remain unchanged. This source builds clock0.4.0, panel0.3.3 and board
baseline1.0.3; shared Springboard, Battery and Settings keep their own exact pinned
source versions in `apps/shared-sources.json`. No Watch copies of those apps exist.

## Behavior

- Clock remains the default application: NOVA12-hour AM/PM, hardware-gauge battery
  percentage (or honestly unknown), fixed UTC+08 RTC source to America/Denver,
  crown light sleep and60-second awake clock inactivity. No screen scrub; the
  completed boot logo holds250ms. Touch activity now resets clock inactivity.
- A fresh single-finger swipe of20 logical pixels starts a six-frame quick fade.
  The clock keeps sampling during the fade, closes its input subscription/grant,
  and requests `springboard.elf`. A held contact continues as drag-only in the
  shared launcher; releasing that inherited gesture never launches an app.
  Gaps, multiple contacts and changed IDs require neutral input before rearming.
- The launcher contains only installed Clock, Battery and Settings. Its icons are
  genuine embedded Font Awesome glyphs. Orbitron/Rajdhani text and all font
  licenses/provenance travel with each ZIP under `shared/`, including the
  separate Settings text subset and RTC ABI/source records.
- Shared app return/Back reloads a fresh Clock invocation under the existing
  runtime lifecycle; there is no hidden application stack. Clock entry/exit
  releases frames and grants; input closes before sleep and reopens after wake
  or refusal. The runtime independently revokes app grants before image unload.
- Settings shows supported time and device information. It reads in Denver time
  and inverse-converts writes to the same fixed UTC+08 RTC basis. A DST spring gap
  is rejected; a repeated fall hour requires explicit MDT/MST choice. Readback
  verifies the raw stored calendar. Unsupported preferences and radios are not
  writable fake controls. No rotary crown navigation provider is claimed.

## First-frame visibility

The old cold-clock path requested brightness before its animation, and panel
resume restored the PWM while old GRAM was still present. The panel now records
requested brightness while dark and restores it only after every row of the
first new frame completes. Partial transfers, failed presentation and failed
unblank stay dark/fail closed. Wake retains the same saved brightness policy.
This is a software-ordering correction; actual visual absence of the flash still
needs observation on the watch. The fix ships only in this combined bundle.

## Exact deployment boundary

Seven instances are selected: GPIO1, shared I2C package independently mapped as
system2 and touch3, PMU4, panel5, FT6336 touch6, RTC8. The two I2C instances share
one package artifact but retain different IDs, controllers and configurations.
No radio/IMU selection, extra rails or unverified hardware is inferred.

Display rotation is180 and its SPI bus is40MHz. Raw touch stays unmodified in
the physical driver; every deployed client explicitly transforms copied samples
by `(239-x,239-y)` before hit-testing. This uses generic client configuration,
not an incompatible hardware-config ABI. Shared apps are built with
`PORTABLE_TOUCH_ROTATION=180` and `PORTABLE_RTC_UTC8_DENVER`; Settings additionally
uses `PORTABLE_SETTINGS_APP`.

Per-app grants are exact: display and touch for all four apps; RTC for Clock,
Springboard and Settings; battery for Clock and Battery. No raw CPU or bus grant
is exposed to an app. The panel reports a20Hz nominal scheduling target only at
40MHz, with typical latency0 meaning unmeasured. This selects the shared compact
presentation; it is not a measured FPS guarantee.

Requires the unchanged paired RiscRTE firmware0.1.2 source
`a3d23da9cdc1b3a66c6429f29781856fa7fc8f75`. Older10MHz runtime images are incompatible.
The full flashing bundle must carry these exact runtime bytes and the matching
bootfs, with component/merged SHA256 checksums. No release or flash is performed.

## Verification and limits

Run driver/release/clock/crown tests, `scripts/test_launcher_clock.py`, then the
four-app target builder and deployment verifier. `scripts/test_launcher_runtime.sh`
executes the production paired runtime, seven real driver instances and all four
real apps against low-level GPIO/I2C/SPI models, including held-entry continuity,
Battery/Settings Back, inverse Settings save/readback and final quiescence. Shared app suites cover UI,
rotation, held-entry safety, spring settling, Settings navigation and DST inverse.
The target ELF validator checks all four application images.

All eight explicit launcher projections are compared byte-for-byte, allowing
only board.revision normalization, before `launcher-common` is produced. Its22
store files include six unique driver artifact pairs and four app pairs. SPIFFS
is unpacked and compared against those exact files. Common means only this
seven-instance closure is identical, not that the radio/IMU variant is known.

Host models and target CI cannot establish physical touch alignment, visual
frame rate, power draw, battery accuracy, crown timing or repeated wake quality.
