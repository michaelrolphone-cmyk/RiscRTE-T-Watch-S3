# Optional NOVA launcher and Settings bundle

This is the optional Watch PR5 line. The accepted PR6 clock0.3.1 and its flashing
bundle remain unchanged. This source builds clock0.4.4, original panel0.3.3 and board
baseline1.0.3; shared Springboard, Battery and Settings keep their own exact pinned
source versions in `apps/shared-sources.json`. No Watch copies of those apps exist.

## Behavior

- Clock remains the default application: NOVA12-hour AM/PM, hardware-gauge battery
  percentage (or honestly unknown), fixed UTC+08 RTC source to America/Denver,
  crown light sleep and60-second awake clock inactivity. No screen scrub; the
  completed boot logo holds250ms before a180ms simultaneous blur crossfade to Clock. Touch activity now resets clock inactivity.
- A fresh single-finger swipe of20 logical pixels hands the last completed sharp
  Clock frame to `springboard.elf`. The shared app performs a180ms blur crossfade
  while continuing the gesture, with outgoing/incoming opacity and sharpness
  reaching their final values together. No black-fade interlude is added. A held contact continues as drag-only in the
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
  writable fake controls. Crown short press is Back outside Clock, including one-level Settings cancel,
  through an app-local adapter over the original PMU event API. There is no new
  provider or rotary behavior. The old PMU cannot report a held key across an app
  boundary before its release; pending completed events are drained on entry.

## First-frame visibility

Clock explicitly requests brightness zero immediately after validating the display
capability, including re-entry while the persistent panel still holds a previous
app frame. It restores brightness only after a complete first intro frame. The
original physically confirmed panel/PMU code is retained unchanged. This prevents
application-time stale-frame exposure; any earlier boot rail/GPIO interval remains
a separate physical observation, not an unverified hardware-fix claim.

## Exact deployment boundary

Seven instances are selected: GPIO1, shared I2C package independently mapped as
system2 and touch3, PMU4, panel5, FT6336 touch6, RTC8. The two I2C instances share
one package artifact but retain different IDs, controllers and configurations.
No radio/IMU selection, extra rails or unverified hardware is inferred.

Display rotation is180 and its SPI bus is40MHz. The confirmed identity touch
coordinates remain unchanged in every client. Shared apps use
`PORTABLE_TOUCH_ROTATION=0`, `PORTABLE_RTC_UTC8_DENVER`,
`PORTABLE_FORCE_FULL_FRAMES`, and the optional local navigation factory. Only
Springboard opts into retained-frame handoff; that is an explicit deployment
contract, not an assumed generic display ABI guarantee.

Per-app grants are exact: display, touch and board.battery for all four apps; RTC
for Clock, Springboard and Settings. The shared app-local crown bridge reads only
the original PMU key-event extension. No raw CPU or bus grant is exposed to an app.
The panel reports a20Hz nominal scheduling target at40MHz, with typical latency0
meaning unmeasured. All presentations transfer the complete240rows.

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

See GUI_INCREMENT.md for the exact unchanged physical-byte inventory and the
separate later deep-sleep scope. Preserve the confirmed0.4.0 images for rollback.
