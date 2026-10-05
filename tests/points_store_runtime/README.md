# Points app → Runtime/service → stored Clock regression

```sh
SANITIZE=1 ASAN_OPTIONS=detect_leaks=0 python3 scripts/test_points_store_faces.py \
  --runtime ../runtime --system-apps ../system-apps --utilities ../utilities \
  --legacy-utilities ../utilities-legacy \
  --metadata-legacy-utilities ../utilities-custom-legacy \
  --productivity ../productivity \
  --archive dist/points-common/twatch-points-launcher-0.8.0-points-launcher-common.zip \
  --output /tmp/points-store-runtime
```

`--store` accepts an extracted, complete production store instead. The original
Clock decoder is Utilities `5418d9dc7f9963d96b5b8b11c40658ee753d9cbd`.
The optional metadata comparator is Utilities `f89fed5` (custom-aware PTM1,
before the 13-character extension). With all three decoders the runner executes
789 scenarios; without the metadata comparator it executes 716.

## Production boundaries

The harness reuses the production-store Runtime/CpuPort/target-ELF-registry
fixture, compiles all selected actual drivers and the current Points service,
and admits unchanged boot, board, app and provider policies. Target executable
bytes are replaced only in a separate native host copy. Original store bytes
and policy JSON hashes are checked before and after.

Runtime first dispatches from Clock to Points. The adapter includes the actual
Points app source and drives its dependency acquisition, load_catalog and
save_action through the real namespace-5 grant. Explicit time preference
changes use the real namespace-1 grant. The real service reconciles through its
bound provider storage. Runtime unloads Points and reloads the actual Clock;
its read/decode/projection/render path is observed before teardown.

## Coverage

- Missing config/meta selects the exact seven temporary defaults, without
  persisting either record. App and Clock independently assert every kind,
  time, duration, weekday mask, notification mode and warning flag.
- Mon–Thu: Wakeup 04:30, Drive to Work 05:30–05:45, Work 06:00,
  Break 09:00–09:15, Lunch 12:00–12:30, Break 14:15–14:30,
  Work End 16:30. Work and Work End remain zero-duration points.
- The actual service's next deadline is checked before each warning:
  09:12, 12:27 and 14:27. Friday/Saturday probes point to next Monday.
- At all seven start times and three warning times, on each Mon–Thu,
  the actual service invokes both real audio/haptic drivers. At the raw
  hardware boundary, one audio open/close and one haptic GO are required;
  the persisted occurrence identifies the exact slot, edge, mode and deadline.
- A separate process restarts with those same persisted records and RTC time:
  no duplicate output or record changes are permitted.
- All corresponding Friday/Saturday times are silent. Actual duration-end
  times 05:45, 09:15, 12:30 and 14:30 are also silent on all six tested days.
- Existing basic schedules and explicitly saved empty records are preserved.
  Error/read-failure records are never repaired with defaults.
- All 33 stored face IDs are retained for basic records; schedule IDs 24–32
  exercise every config/metadata data state and latest 12/24-hour preference.
- Short labels encode compatibly as PTM1. The full 13-character Drive to Work
  label survives PTM2 on the current reader; the old PTM1 reader safely falls
  back. Forged PTM1 length 13 and PTM2 length 14 fail bounds checks, retaining
  valid schedule data with generic labels.
- Legacy Clock reproduces the original custom/end/warning decoder mismatch.
  Current Clock accepts those records without storage conversion.

Namespace-5 config/meta must not be written by default loading. Namespace-4
occurrence writes are expected service behavior: expiration, delivery and
restart deduplication require durable state. `POINTS_STORAGE` diagnostics
report these separately from audio/haptic observations. Malformed config cases
use a raw crown-release event to dismiss the real service error modal.

`points-results.json` contains every scenario and diagnostics; `provenance.json`
contains store custody, Runtime/Watch/System/Utilities source state, registry
provenance and sanitizer configuration; `points-provenance.json` adds app and
legacy source state, adapter hashes and a source-unchanged check.

Limits: native architecture, not target Xtensa execution or physical device
qualification. The app event/render loop is outside this fixture; its real
load/save functions are driven directly. GUI tests cover interaction dispatch.
This fixture reloads default Clock rather than navigating the launcher-return
entry. Historical PTO1 ledger codec migration is covered separately.
