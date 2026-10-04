# Points in Time development integration

Clock 0.7.0 adds a fifth SCHEDULE category with eight companion faces, IDs24–31.
The original24 IDs retain their identity and original pixels. The separately
owned Productivity app configures recurring Work Start, Work End, Lunch, Break
and Bedtime points. It starts with an empty catalog; attachment times and battery
values are illustrative design data only.

## Ownership and limits

- Productivity owns the app and explicit user edits. Utilities owns the compact
  record codecs, daily recurrence, durable occurrence ledger, output arbitration,
  recovery, acknowledgement and sleep deadline selection.
- Eight independently enabled point slots, each with selected weekdays and local
  hour/minute. More than one Break/Lunch is allowed. Lunch/Break can have an
  elapsed duration of0–720 minutes; zero means no automatic end notification.
- A per-point mode selects System default, vibrate, sound or both. The existing
  Settings alert_mode is the default. Clock-time labels follow Settings12/24h,
  defaulting to12h with explicit AM/PM.
- Eight slots fit one64-byte configuration record and one64-byte occurrence
  ledger within existing Runtime limits. No firmware scheduling, new firmware
  ABI, Runtime change, background task or timer provider is added.
- Saving any point creates a new catalog revision. It cancels pending events and
  duration ends from the previous catalog, and only future starts are eligible.
  The app discloses this before saving. An unconfirmed save locks edits until
  the identical bytes are successfully read back or the app is reopened.
- Recurrence uses the established fixed-UTC+08 RTC / America/Denver conversion.
  Nonexistent and repeated DST civil times are skipped, never silently mapped
  to an arbitrary offset. Duration ends add elapsed minutes to a valid start;
  their selected weekday is the parent's start day, even across midnight/DST.

## Foreground, sleep and rendering

The original ordinary alarm.service@1 copied status/token/sleep ABI is unchanged.
The opt-in0.2.0 service uses existing output and failure-only cleanup phases.
Named Points alerts use the existing retained foreground modal in all apps;
Clock retains its picker state, cancels stale input, and starts a fresh60-second
idle period after dismissal. The Points app owns nested Back navigation; only a
root-level Back requests Springboard, and uncertain saves cannot trigger a
queued handoff.

Clock reads the catalog once per fresh invocation, before any frame is acquired,
and releases the grant before sleep. It projects copied configuration with the
same Utilities recurrence functions in a separate translation unit. Projection
and rendering never write storage or schedule work. Invalid RTC clears stale
schedule displays, including a same-second recovery. Actual active overlapping
Lunch/Break intervals determine STATUS; no missing work pair is fabricated.

Sleep preparation remains a fresh service reconciliation at a settled display
boundary. Native-retained(-2) results bypass cleanup/provider calls. No storage,
RTC or service work occurs after the Deep hold. Existing typed panel-resume,
light-to-deep, refused sleep and fresh-boot paths remain intact.

## Exact deployment authority

The new explicit points-launcher profile contains ten app policies and40 store
files. Clock has namespace1 preferences plus namespace5 Points read access. The
Points app has namespace5 catalog access and namespace1 preference reads. Other
apps keep their existing grants. No app receives raw audio/haptic grants.

The ordinary service binds exactly seven keys: existing alarm_cfg/timer_cfg
(namespace3 read), alarm_occ/timer_occ(namespace4 read-write), alert_mode
(namespace1 read), plus points_cfg(namespace5 read) and points_occ(namespace4
read-write). The unchanged Runtime admits16 app policies, at most8 grants per
app,8 bound keys and64 bytes per value.

## Source and artifact evidence

apps/points-sources.json pins all four shared repositories. The original driver
package hashes and Runtime0.1.8 pair are unchanged. Points common-store custody
requires all eight board profiles, reconstructs each original input archive,
normalizes only board.revision, and verifies exact manifests, grants, service
bytes and source identities. SPIFFS is packed and unpacked with the pinned tool.
Final BIN assembly requires an external exact-head hosted CI receipt and the
reviewed source tree; it does not accept local-only success as hosted evidence.

Tests cover normal and sanitizer app/service failures, CRC-valid impossible
ledgers, backward RTC reset/replay, uncertain writes/ACK, output cleanup, weekdays,
DST, midnight, duration boundaries, overlapping phases and storage limits. A
worst-case mixed overdue load settles in53 phases, below the64-step foreground
bound. All192 picker interruption cases and the61-second alert/full60-second
idle budget remain tested. Real Runtime/CpuPort/service cross-layer tests run
both normally and with ASan/UBSan; local LeakSanitizer may be disabled only for
the executor's ptrace restriction, while hosted CI uses normal defaults.

These are software, target-layout and artifact checks. Physical wake reliability,
audio/haptic levels, touch feel, power loss and current draw remain unqualified.
No merge, release or device operation is part of this change. Whole-image
installation replaces the lower8MiB including erased NVS and resets saved
settings, Stopwatch, alarms, countdown and Points records; upper8MiB is untouched.
