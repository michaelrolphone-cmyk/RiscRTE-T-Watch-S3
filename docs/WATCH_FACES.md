# Clock 0.6.2: eight faces and picker (development)

This is an app-only increment based on accepted Watch product 1.0.0 source
`f07f33e8e1726fbe1ae49e01bf5a23d0a72c038a`. It does not modify or republish that
release, its firmware, physical drivers, shared app versions, grants, timezone,
sleep policy, panel transport, or crown long-press behavior. Hardware acceptance
and combined alarm integration are separate gates.

## Supplied design inventory

The two original owner-supplied HTML files are retained byte-for-byte in
`apps/clock/faces/reference/`. Both contain the same eight 240x240 faces, ordered
NOVA, ANALOG, RADAR, HEX, TERMINAL, MINIMAL, BINARY, CHRONO. Their actual SVG
geometry was rendered and visually inspected before implementation.

- NOVA: cyan ticks, seconds ring, date, large digital time, battery bar
- ANALOG: white hour/minute hands, orange seconds, date and battery
- RADAR: green grid/sweep, four blips, digital time and segmented battery
- HEX: purple hexagonal seconds progress, stacked hours/minutes
- TERMINAL: monospaced time, date, uptime, battery blocks, amber cursor
- MINIMAL: red accents and seconds bar, wide digital time
- BINARY: six BCD columns for HH:MM:SS, conventional time below
- CHRONO: white/orange analog hands, seconds and date subdials

The reference picker uses 132px preview cards at y92, a 108px pitch, side-card
scale/opacity and edge fading, name/status at y183/y201, and eight dots at y222.
The same production face renderer paints full faces and every card.

Dynamic values use the existing RTC wall-time conversion and battery capability.
The new reference faces display 24-hour values. No RTC writes occur. Missing
telemetry shows dashes/TIME UNSET and empty unknown battery bars rather than the
HTML examples' constant 84%. The Terminal heading reads `> RISCRTE`, avoiding
its mock operating-system version. Small RGB565 quantization/raster differences
remain; no runtime SVG, network font loading, floating point or new driver is used.
OFL font sources/licenses are retained in `nova/fonts`; generated subsets are
reproducible with `python apps/clock/faces/generate_assets.py` and Pillow.

## Interaction and lifetime

Hold a clock contact for 600ms with no excursion greater than 8px to open.
A 20px movement still starts the existing Springboard handoff. Movement outside
the hold slop permanently cancels that hold, even if the finger returns. A tap,
preheld contact on entry, dropped sample, multitouch, contact ID replacement and
the opening release cannot launch or select accidentally.

Swipe horizontally to browse. An off-center card tap centers that card; a center
card tap saves it and immediately returns to the selected full-screen face after
readback succeeds. Failed saves stay in the picker with SAVE FAILED. Short crown
also dismisses the picker. Long crown
retains its prior sleep behavior; inactivity also retains the accepted timeout.
Both close the transient picker before sleeping. No display lease or setting
grant is retained through sleep, application switch or a pending present.

The supplied spring equations run at deterministic 60Hz simulation ticks,
independent of display transfer duration: progressive resistance
`delta/(1+overshoot/24)`, near-edge friction, -0.09 displacement acceleration,
0.8 outside damping, and 0.84 snap easing. Catch-up is bounded to six ticks after
a long stall. A released gesture never becomes a selection while coasting. The reference's brief 334ms, 8% sine pulse remains available while a selection is pending;
successful save now closes immediately per owner feedback. RADAR blips decay after
the sweep passes. A queued selection captures its face ID at the touch release,
so a later side-card tap during an in-flight frame cannot change what gets saved.
Crown close/sleep cancels queued selections.

`storage.key-value@1`, existing explicit instance 1, stores a four-byte versioned
`watch_face` record (magic0x46, schema1, index0..7, xor checksum). This does not
change `sleep_mode` or any other app data. Missing/corrupt/unavailable records
choose NOVA. Writes are skipped if already identical and confirmed by readback;
failed save leaves the prior in-memory selection and visibly reports SAVE FAILED.
No persistence is promised across erase/reflash. Picker scratch allocation failure
keeps the clock available; its single bounded three-slot cache exists only while browsing.

## Focused performance correction after device feedback

The owner accepted 0.6.0's appearance but reported slow scrolling/animation.
The picker previously drew one full face and erased it, then rendered up to five
candidates including wholly offscreen cards. 0.6.2 validates without rendering
and culls exact post-pulse card bounds first. Only the focused card animates;
one or two visible neighbors reuse frozen full-resolution pixels. Neighbor caches
refresh on first visibility or changed minute/date/battery/telemetry validity.
Second, subsecond and monotonic animation changes do not invalidate them.
One checked allocation owns all three slots (345,600 pixel bytes plus metadata),
with balanced cleanup and a Clock-preserving failure path. The standalone clock always rendered only its active face.

Long diagonal strokes previously tested their whole rectangular bounds. The
same four coverage samples now run only within conservative per-row capsule
bounds. This preserves exact anti-aliasing/endcaps, while a representative
216px diagonal checks over 15 times fewer pixels. No geometry, animation clock,
physics, frame pacing, LCD transport or PMU changes are involved.

A focused host timing comparison showed roughly 1.6–6.7 times faster picker
rasterization and 2–3.6 times faster ANALOG/RADAR/HEX/CHRONO rasterization; simple
text faces were essentially unchanged. These are host CPU results, not measured
watch frame rates. 96 full-frame goldens from delivered 0.6.0 remain byte-identical;
tests also compare 2085 strokes against the original rasterizer and enforce one
active-face render, one live focused card in steady browsing, at most three
initial/invalidated visible renders, and exact neighbor freezing/focus activation.

## Verification

- `python scripts/test_watch_faces.py`: all eight production RGB565 renders,
  canary/stride/short-buffer checks, unknown telemetry, hold/swipe/jitter/drag,
  event gaps, ID replacement, timer wrap, resistance and identical 8/20/50/95ms
  frame trajectories; every stored ID, corruption and failed I/O
- `python scripts/test_launcher_clock.py`: production application lifecycle,
  opening-release suppression, carousel save/failure, crown dismissal, restored
  selection in a fresh invocation, existing retained handoff and 8ms touch polls
- Existing crown, return, deep/hybrid sleep, timezone and renderer regressions
- Actual pinned GCC8.4 Xtensa builds, ELF exports/imports and all eight deployment
  profiles; `verify_face_picker_increment.py` requires exactly four changed
  Clock ELF/manifest files and 24 byte-identical accepted store files

`dist/watch-faces` contains authentic host-rendered RGB565 previews, not device
photographs. The owner accepted the physical appearance of 0.6.0; improved 0.6.2 device
responsiveness and power draw still require physical confirmation.
