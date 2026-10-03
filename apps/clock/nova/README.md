# NOVA-7 clock renderer

This is the supplied 240×240 watchface translated into a bounded, portable C
RGB565 renderer. It does **not** interpret HTML/SVG or query hardware at runtime.
The original HTML is retained under `reference/` solely as a design fixture.
Its `84%` and `SYNCED` strings are placeholders, never runtime defaults.

## Visual behavior

- Exact Orbitron 700 time glyphs; Orbitron 500 detail/battery glyphs; Rajdhani
  600 date and Rajdhani 500 labels. The immutable font files are SIL OFL licensed.
- Original tick geometry, corners, divider, cyan arc/white orbit dot, date,
  battery placement and glow. Antialiased RGB565 is necessarily quantized.
- Radius-82 `2 7` dashed ring rotates clockwise every 90 seconds. Radius-76
  `24 60 6 60` ring rotates counterclockwise every 40 seconds.
- Clock defaults to 12-hour time. `12:00 AM` is midnight; `12:00 PM` is noon.
  The AM/PM indicator occupies the status row without resizing the main clock.
- `RTC` means the supplied RTC reading passed calendar validation. It is not a
  network synchronization claim. Invalid time shows `TIME UNSET`, `--:--`, an
  amber status dot and no seconds arc/dot. The renderer does not invent a zone.
- Battery `0%` is a real empty reading. Invalid/unavailable/out-of-range readings
  show `--%` with no green fill. No voltage-derived estimate is made here.
  The initial clock 0.3.0 board driver returned 255/PROFILE_MISSING. Clock
  0.3.1 reads the existing hardware gauge with documented admission checks;
  unavailable still shows `--%`. See docs/PMU_BATTERY.md. The 84% examples are
  explicitly test inputs.

## Integration contract

Compile `nova.c` with the same C SDK includes as the existing clock renderer.
Only `memcpy` and `memset` are undefined in a freestanding optimized host object;
there are no float, trig, allocation or 64-bit division dependencies. Verify
Xtensa imports in the normal target build as host imports are not target proof.

`nova_watch_render(surface, &state)` writes only the 240×240 active area of a
validated little-endian RGB565 surface. It preserves stride padding and guards
and rejects bad format/size/overflow before writing. It does no capability I/O.

The caller owns state:

- `time`: the selected RTC wall-time fields, already adjusted by any future
  shared timezone/settings contract.
- `time_valid`: RTC read succeeded; calendar validity is checked again here.
- `subsecond_ms`: explicit RTC-anchored fractional phase, 0–999. Values above
  999 clamp rather than silently changing civil seconds.
- `animation_ms`: monotonic elapsed phase for the two rings. It is independent
  of civil time. A uint32 wrap safely restarts phase; it never corrupts memory.
- `battery_valid`: PMU read succeeded, percent <=100 and the profile-missing flag
  is absent. `battery_percent` is the original PMU sample, including real zero.

The app owns boot animation, crown handling, rotation, sleep/wake, display
submissions and cadence. Do not change those in this renderer. The same supplied
state may render an outgoing ripple frame. Fresh RTC/PMU validity must be
re-established after wake; this renderer never substitutes stale validity.

Include `fonts/Orbitron-OFL.txt`, `fonts/Rajdhani-OFL.txt` and `fonts/SOURCES.txt`
in the final deployment ZIP alongside other license/provenance documents.
Font binaries are needed only to regenerate assets, not to run the firmware.

## Reproducible host checks

From repository root:

    python3 apps/clock/nova/tests/run.py

This compiles strict C11 normal and AddressSanitizer/UBSan variants. The traced
host requires LeakSanitizer disabled; the renderer allocates nothing. Tests
cover noon/midnight, AM/PM, leap dates, calendar rejection, 59→00 arc rollover,
colon phases, explicit subsecond clamping, ring periods, zero/unknown battery,
tight/padded frames, malformed surfaces and untouched buffer guards.

To render fixtures after those checks:

    python3 apps/clock/nova/tests/render_previews.py OUTPUT [REFERENCE_PNG]

Each example is a host framebuffer, not a physical watch photograph. The GIF
shows animation phases from 18 to 21 seconds using a fixture 84% reading.

`generate_assets.py` regenerates `assets.inc` from retained SVG/font inputs using
Pillow, numpy and Inkscape. Runtime code does not require those tools. Glyphs and
static geometry are cached offline; each frame uses sparse geometry, bounded
mask sampling and row clearing. `assets.inc` is checked in so normal firmware
builds need no font download or rasterizer.

## Host measurements (2026-10-03)

4,223 checks passed in both normal and sanitizer runs. On this cloud host an
optimized build rendered 2,000 frames at approximately **0.083 ms CPU/frame**;
the sanitizer build took approximately 0.20–0.29 ms. These numbers are **not physical
watch FPS**, panel throughput, target CPU timings, or promises about battery use.
A freestanding optimized host object measured 111,778 text/rodata bytes, zero
mutable data/BSS. Normal tests also verify stride-480 vs stride-484 equivalence.
Target build and on-device confirmation remain separate integration checks.
