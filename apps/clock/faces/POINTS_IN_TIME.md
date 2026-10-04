# Points in Time companion faces

Stable IDs 24–31 are NEXT, RING, LADDER, DAYLINE, TRIPLE, STATUS, BOARD,
and WORKDAY, in the fifth SCHEDULE picker category. IDs 0–23 keep their
original meaning and pixels. The existing cyclic picker mechanics are unchanged.

## Render data contract

`points_state.h` is a plain-C read-only snapshot. `nova_watch_state.points`
points to app-owned storage that remains valid for the complete render call.
The app builds the snapshot outside rendering from the persisted daily-point
records and shared recurrence policy. The renderer does no capability lookup,
I/O, allocation, local-time conversion, service mutation, or global-state update.

- All `*_rtc` fields are uint32 absolute seconds since 2000-01-01 on the same
  RTC axis. Countdown and phase/work progress use these fields, never local
  wall-clock subtraction. DST jumps, repeated hours, and midnight are therefore
  caller-resolved before presentation.
- Event hour/minute/day offset are already converted to the selected local
  wall time. Scheduled clock labels follow the current global 12/24-hour
  setting, defaulting to 12-hour with each event's own AM/PM. Future-day labels
  include a day suffix where the design has a clock label.
- `next[4]` is ordered, with absolute deadlines at or after now. `today[16]`
  contains actual local-today edges in absolute order, including duration ends.
  Bounds, event kinds, source slots, civil hours/minutes and ordering are checked.
- Kinds match shared persisted values: Work Start 1, Work End 2, Lunch 3,
  Break 4, Bedtime 5. Only Lunch/Break ends display BACK. `source_slot` preserves
  record identity so overlapping same-kind records cannot steal one another's
  interruption endpoints. WORKDAY bands use only matched real endpoints that
  are present in today's projection; no missing past/future bands are guessed.
- The caller provides current phase, previous edge and a real Work Start/End
  pair. Missing, zero-length and reversed pairs show NO WORK PAIR. A real
  completed pair displays WORKDAY COMPLETE.
- NULL or UNAVAILABLE means unavailable; EMPTY means no configured points;
  ERROR or malformed projection means schedule error. Invalid RTC suppresses
  all stale schedule information and displays TIME UNSET. READY with no next
  edge displays NO UPCOMING, and an empty today list displays NO POINTS TODAY.

`revision` is stable across animation/seconds and changes on config reload,
edit, timezone/selection changes, event/phase advance or availability changes.
The picker copies revision, next deadline, status and phase by value: comparing
old pointers would miss an in-place snapshot update. Schedule changes invalidate
only schedule-card slots. Minute/date/clock-policy/telemetry changes keep their
existing invalidation behavior. Only the focused face updates every frame;
at most six visible cards are cached, including a vertical category transition.

## Deliberate source adaptations

The HTML's fixed example schedule, meetings/GYM and example battery percentage
are never included in firmware data. Every displayed point comes from the
snapshot. Battery bars use the existing valid PMU sample, including real zero;
unknown battery also displays BATT --%.

Large countdowns retain hours beyond 24. Compact countdowns are consistently
H:MM, explicitly labeled in TRIPLE/BOARD; LADDER uses IN nH nnM / n MIN.
DAYLINE spans the full local day rather than clamping every pre-06:00 point to
the left edge. Labels alternate rows with bounded collision resolution while
ticks retain their true local clock position. The supported maximum eight
point starts and sixteen edges cannot overrun a frame.

Fonts are offline subsets of the already retained OFL Orbitron and Rajdhani
files. `generate_points_assets.py` reproduces `points_assets.inc` (26,520 alpha
bytes); no web/font engine is used on the watch. All geometry is integer
RGB565 with clipped primitives and bounded string buffers.

## Alert title entry point

`nova_watch_alarm_label_render(surface, label, countdown, blocked, rtc_error,
dismissing, uncertain, occurrence)` accepts a bounded service title (at most
23 bytes). NULL/empty uses the original ALARM/COUNTDOWN title. The existing
`nova_watch_alarm_render` wrapper retains its previous rendered bytes.

## Verification

From the Watch repository root:

    python3 scripts/test_points_watch_faces.py
    python3 apps/clock/nova/tests/run.py
    python3 scripts/render_points_reference.py /path/to/watchfaces-schedule.html

The Points suite compiles the actual production C with ASan/UBSan. It covers
18 scenarios × eight faces, tight/padded stride equivalence, surface rejection,
untouched guards, zero/full-uint32 and >24-hour durations, day offsets, noon/
midnight, DST-derived repeated-hour input, bounded counts, invalid input,
unavailable/empty/error/no-pair states, in-place picker invalidation, overlapping
same-kind record matching, existing-face independence and bounded alarm titles.
The production frame sheets are in `dist/points-native`; each one is labeled
as synthetic TEST INPUT, not a photograph or device frame capture. The offline
owner HTML raster is labeled as illustrative reference data.

During integration, 168 old production frames (all 24 original faces across
seven clock/telemetry policies) were compared directly with the unmodified
1d2eb1cd baseline and remained byte-identical. A freestanding host object has
only memcpy/memset unresolved symbols; target imports and physical watch
performance remain separate integration checks.
