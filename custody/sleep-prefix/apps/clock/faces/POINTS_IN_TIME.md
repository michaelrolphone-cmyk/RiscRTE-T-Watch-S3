# Points in Time companion faces

Stable IDs 24-32 are NEXT, RING, LADDER, DAYLINE, TRIPLE, STATUS, BOARD, WORKDAY and UP NEXT in the fifth SCHEDULE picker category. IDs 0-23 keep their original meaning and pixels.

## Render data contract

`points_state.h` is a plain-C read-only snapshot owned by Clock for the complete render call. The renderer performs no capability lookup, storage I/O, allocation, time-zone conversion, service mutation or scheduling.

- All `*_rtc` fields use absolute seconds since 2000-01-01. Countdown/progress arithmetic never subtracts displayed wall-clock values.
- `next[4]` and `today[16]` contain visible schedule start/end edges only. The 3-minute warning is a notification cue and is intentionally not projected as another face event.
- Built-in kinds are Work Start, Work End, Lunch, Break and Bedtime. Custom kinds 6 and 7 carry a bounded 12-character label and one of eight palette indices in each projected event.
- Custom duration starts/ends behave like other duration intervals for ring/marker geometry while retaining their own label and color.
- `source_slot` preserves identity so overlapping duration records pair with their own end.
- Workday calculations continue to use only real Work Start/Work End pairs; custom points never fabricate work state.
- NULL/UNAVAILABLE, EMPTY, ERROR and invalid RTC suppress stale schedule information exactly as before.

The projection revision includes both schedule and custom-metadata revisions. Changing only a custom name/color therefore invalidates schedule cards without altering recurrence or creating a cue.

## NOVA-7 UP NEXT

UP NEXT is stable face ID 32 and follows the supplied mockup's visual model: 60 perimeter ticks, live seconds sweep, point dots and duration arcs, NOW/NEXT status, active/next countdown, progress bar, THEN event and segmented battery. It consumes only live projected Points data; illustrative mockup times and battery values are never embedded.

Points notifications do not force an overlay on this or any other watch face. A face may naturally show the point that is currently active or upcoming. Alarm/Countdown retain their separate modal renderer.

## Rendering constraints

Fonts are offline subsets of the retained OFL Orbitron and Rajdhani assets. Geometry is bounded integer RGB565. Unknown battery remains unknown rather than receiving a fabricated percentage. Large countdowns retain hours beyond 24, and 12/24-hour labels follow Settings.

Verification exercises all nine schedule faces across configured, empty, unavailable, error, RTC-unset, DST, midnight, long-duration, clustered-edge and custom metadata scenarios; it also checks tight/padded surfaces, guards, picker cache invalidation and independence of the original 24 faces.
