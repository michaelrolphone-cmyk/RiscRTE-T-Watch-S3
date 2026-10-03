# Optional NOVA launcher and Settings bundle

This is the optional Watch PR5 line. The accepted PR6 clock0.3.1 and its flashing
bundle remain unchanged. This source builds clock0.4.2, panel0.3.5, PMU0.4.1 and board
baseline1.0.5; shared Springboard, Battery and Settings keep their own exact pinned
source versions in `apps/shared-sources.json`. No Watch copies of those apps exist.

## Behavior

- Clock remains the default application: NOVA12-hour AM/PM, hardware-gauge battery
  percentage (or honestly unknown), fixed UTC+08 RTC source to America/Denver,
  crown light sleep and60-second awake clock inactivity. No screen scrub; the
  completed boot logo holds250ms. Touch activity now resets clock inactivity.
- A fresh single-finger swipe of20 logical pixels starts an80ms brightness fade.
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

Version 0.4.1 was reported to remain black on the physical watch. Version
0.4.2 restores the known-working 0.4.0 PMU rail startup/teardown policy and removes
all dynamic backlight-rail operations from the panel. In particular, frame
completion no longer depends on a new 1 ms I2C write. The optional PMU API suffix
is retained for compatibility and uses the normal 40 ms register-write budget.

The panel still claims its GPIO with the OFF latch and keeps PWM dark until
all 240 fresh rows complete, including cold activation, wake and app handoff.
Failed rows/PWM restoration still fail closed. The 0.4.1 input, crown Back,
partial-update and tap fixes remain unchanged.

This is a bounded rollback of the newly failing power path, not a claim that
the physical failure was proved in a host model. The reported old-frame startup
flash remains open, and both recovery and flash absence need watch observation.

## Exact deployment boundary

Seven instances are selected: GPIO1, shared I2C package independently mapped as
system2 and touch3, PMU4, panel5, FT6336 touch6, RTC8. The two I2C instances share
one package artifact but retain different IDs, controllers and configurations.
No radio/IMU selection, extra rails or unverified hardware is inferred.

Display rotation is180 and its SPI bus is40MHz. Raw touch stays unmodified in
the physical driver; every deployed client explicitly transforms copied samples
using identity coordinates before hit-testing. LILYGO normal orientation already
mirrors the panel and applies the80-row gap while returning raw FT6336 coordinates;
a second180-degree touch rotation was incorrect. This uses generic client configuration,
not an incompatible hardware-config ABI. Shared apps are built with
`PORTABLE_TOUCH_ROTATION=0` and `PORTABLE_RTC_UTC8_DENVER`; Settings additionally
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
only board.revision normalization, before `launcher-common` is produced. Its24
store files include seven unique driver artifact pairs (one logical) and four app pairs. SPIFFS
is unpacked and compared against those exact files. Common means only this
seven-instance closure is identical, not that the radio/IMU variant is known.

Host models and target CI cannot establish physical touch alignment, visual
frame rate, power draw, battery accuracy, crown timing or repeated wake quality.

## Physical-feedback correction0.4.1

The user reported reversed Springboard/Settings movement, slow fade/stutter,
Battery appearing unresponsive, and a remaining startup flash on0.4.0. These
reports supersede the earlier host-model result;0.4.0 is preserved for comparison.
Shared clients now sample input while a frame is in flight, coalesce movement
without losing a completed fresh tap, and avoid sleeping again for time already
spent presenting. An optional previous-frame cache computes bounded changed-row
damage; allocation failure falls back to full frames. The panel transfers those
rows, but always forces a complete first frame after blanking/wake.

`pmu-navigation` is a logical ELF with no hardware instance, depending on the
sole selected PMU owner. It translates a fresh down→short-release sequence into
existing `input.navigation@1` Back. All shared apps receive that explicit grant;
Clock retains its sleep policy. Reset/foreground changes discard stale sequences.
Crown Back works even if touch reads fail; Settings subpages cancel/back one level
without saving, root returns to Clock. Clock drains the returned key event before
arming sleep. No rotary navigation or new runtime ABI is asserted.

Center and first-ring icons center/open from one tap. Farther icons center only;
a subsequent tap opens. Hit testing and ring classification use the last visible
geometry rather than an unpresented physics position. Slow valid frames no longer
cancel a deliberate pending launch.

Primary coordinate reference: LilyGoLib92f2ac3f `src/display/LilyGoDispInterface.cpp`
normal rotation uses panel mirrors and gap80; `src/LilyGoWatchS3.cpp` returns
FT6336 points without another coordinate flip. Physical confirmation of the new
binary remains necessary; software timing models are not hardware FPS claims.
