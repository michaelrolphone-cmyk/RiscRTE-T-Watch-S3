# Points in Time development integration

Clock 0.8.0 keeps the fifth SCHEDULE category and adds the owner-supplied NOVA-7 UP NEXT face as stable ID 32, for nine companion faces across IDs 24-32. IDs 0-31 retain their identity, so existing persisted selections are not renumbered.

The separately owned Productivity app configures eight recurring Points slots. The built-in set remains Work Start, Work End, Lunch, Break and Bedtime. Points in Time 0.3.0 uses the NOVA-7 black/cyan presentation, chronological scrolling list, edit rows, day presets, drum-style time/duration controls, two reusable custom point types, and the mockup's eight-color custom palette.

## Ownership and records

- Productivity owns explicit point edits and the display-only custom type metadata.
- Utilities owns the compact record codecs, recurrence, durable cue ledger, output arbitration, recovery and sleep deadline selection.
- The main `points_cfg` record remains exactly 64 bytes. Each slot now stores independent Notify at End and 3 Minute Warning bits in previously unused flag bits.
- Two reusable custom kinds occupy the remaining persisted kind values. Their names (up to 12 characters) and palette colors live in a separate 64-byte `points_meta` record. Metadata never controls whether a cue fires.
- The occurrence ledger remains exactly 64 bytes. PTO2 stores one parent-day cursor plus delivered bits per slot so Start, 3 Minute Warning and End are independently durable. Existing PTO1 ledgers decode forward.
- Eight independently enabled point slots retain selected weekdays, local hour/minute and per-point System default / Vibrate / Sound / Vibrate + Sound mode.
- Lunch, Break and custom points may have elapsed durations of 0-720 minutes. Notify at End requires a nonzero duration. 3 Minute Warning requires at least three minutes and remains independent of Notify at End.
- Saving schedule changes creates a new catalog revision and cancels pending events from the old schedule. Metadata changes alter only custom labels/colors.

## Notification behavior

Points are notifications, not alarms. A due Start, enabled End, or enabled 3-minute warning produces one short self-completing cue: a wrist haptic tap, a brief watch beep, or both according to the point's selected notification mode. System default resolves through the existing Settings alert mode.

Normal Points cues do not publish `ALARM_STATE_ALERT`, do not expose a modal occurrence, and do not invoke the retained Alarm/Countdown overlay. Output cleanup and durable replay still apply if an output or storage operation fails. Alarm and Countdown retain their existing modal behavior and ABI.

The 3-minute warning is service-only; it does not become an extra visible schedule edge. Watch faces may show the real point start/end state and countdown naturally.

## Clock projection and rendering

Clock reads `points_cfg` and optional `points_meta` once per fresh invocation and releases the grant before sleep. Invalid or unavailable metadata falls back to generic CUSTOM 1 / CUSTOM 2 labels and cyan without invalidating recurrence. Custom metadata revision participates in the schedule render cache, so label/color edits refresh the schedule faces.

Projection uses the same Utilities recurrence implementation and exposes start/end edges only. Custom labels and colors travel in the read-only render snapshot. No renderer performs storage I/O, capability lookup, scheduling or output.

The UP NEXT face uses the supplied NOVA-7 geometry: perimeter minute ticks, live seconds sweep, point markers and duration arcs, NOW/NEXT state, countdown, progress bar, THEN line and real battery segments. No notification overlay is added.

## Deployment authority

The explicit Points launcher grants Clock namespace 5 read access and the Points app namespace 5 read-write access plus namespace 1 preference reads. No application receives raw audio or haptic capability. The service remains the only output owner.

The service still binds exactly seven keys: alarm_cfg/timer_cfg (namespace 3 read), alarm_occ/timer_occ (namespace 4 read-write), alert_mode (namespace 1 read), points_cfg (namespace 5 read), and points_occ (namespace 4 read-write). `points_meta` is deliberately not service-bound because it is presentation metadata only.

## Verification

The source pins in `apps/points-sources.json` identify the exact System Apps, Utilities, Runtime and Productivity inputs. Tests cover the main schedule codec, custom metadata codec, PTO1-to-PTO2 compatibility, independent Start/Warning/End delivery, sleep deadlines, output modes, replay without duplicate cues, app uncertainty handling, custom UI behavior, clock projection, custom labels/colors and the production schedule faces.

Physical haptic feel, speaker loudness, wake reliability, power-loss behavior and current draw still require hardware qualification. No merge, release or device operation is performed by this change.
