# Watch 1.0.12 runtime feature candidate

This separate `runtime-features` build lane starts from the physically accepted
Watch 1.0.11 full 22-app RF/power cohort. It does not replace that delivered image,
publish a release, or claim physical qualification for the new increment.

## Applicable mechanisms

- The Clock uses Runtime's native UTC realtime for its regular face readings and
  fractional phase. Cold/reset and ordinary app-return recovery use the accepted
  fixed UTC+08 hardware RTC convention. Existing Denver presentation, alarm/Points
  civil basis and settings remain unchanged. Native RTC retention avoids reseeding
  on classified deep wake. Invalid/unset time is never fabricated. Dates outside
  the native signed-32-bit epoch range continue through the accepted hardware RTC
  read path, retaining Watch's 2000–2099 calendar domain.
- The default Clock stages a one-byte, app-owned continuation record while its
  retained-wake grant is live. Runtime commits it only at terminal deep entry.
  A matching, consumed checkpoint on classified deep wake skips the cold logo and
  renders a complete fresh Clock frame while dark before restoring brightness.
  Cold/reset, incompatible schema, foreign app/cohort and invalid payload all use
  ordinary startup. Every returning/refused sleep cancels staged continuation.
- Demand activation is explicit in the new boot profile. The default acquires its
  needed closures, presents a safe frame, then promotes the full validated graph
  before paired boot confirmation. This preserves alarms and provider-owned
  telemetry through ordinary navigation. Failed promotion cannot confirm a pair;
  unsafe cleanup retains the invocation using Runtime's public terminal fence.
- Outbound BLE enumerates the selected telemetry capability and supports all seven
  current generic metrics. This Watch source exposes real battery percentage,
  voltage and charging readings only; it exposes no temperature field. Packet
  capacity omissions are explicit in status. The generic telemetry provider performs the bounded advertising;
  provider-owned state survives ordinary app switches. Existing Bluetooth,
  Airplane and low-battery policy remain authoritative. Foreground scanner/HID/SDR
  work and sleep pause broadcasting; a healthy awake app resumes it afterward.
  The Battery screen exposes the saved enable/disable choice and actual status.
  Nearby receivers can read these open broadcasts without pairing.
  Timecard and Spectrum/RF pause publication before app-data operations. Native
  retained storage outcomes permit no further radio/storage I/O; uncertain BLE
  cleanup fences the Runtime invocation before storage can begin.

## Started signal capture stays awake

Audio Spectrum retains its existing app-local continuous-capture idle guard.
Waterfall now opts into the analogous shared radio capture predicate, using its
real requested/running/owned/healthy state. Automatic touch-inactivity sleep is
inhibited only while the input is active. Stop, capture failure and app exit
remove the condition. Raw SDR still requires the native Bluetooth modem to be
idle; an enabled Bluetooth preference is never silently overwritten. Explicit sleep/suspend still closes the input normally;
this change introduces no automatic radio restart or persistent inhibitor.

The actual RF controller/adapter is tested without touches across 61-second and
10-minute jumps, then through stop, capture failure, retry and app reentry.
Actual Audio Spectrum/adapter is tested across 9,000 polls, including empty
input recovery, while its shared lifecycle suite checks explicit sleep and stop.
Both paths run normally and under ASan/UBSan.

## File-open applicability

Runtime's canonical file-open handoff requires `/sd/` data paths and installed
applications that declare compatible file types. The accepted Watch Files
application browses read-only installed files and supplies neither an SD volume
nor compatible receiver applications. This increment therefore adds no unusable
file-open grant, invented SD provider or fabricated handler.

## Verification scope

`test_clock_runtime_features.py` exercises the exact feature client through
production Runtime/CPU/dlopen: native recovery and reads, demand/promotion,
terminal deep entry, classified wake, refusal, unexpected return, native time
errors, reset, corruption and foreign identity. Its pure calendar comparison
checks 333,563 accepted RTC hours through the native epoch boundary against the
unchanged Watch display conversion, plus out-of-native-range fallback. Normal
and ASan/UBSan runs are required. Actual Clock ELFs use GCC 8.4, validated target
headers/exports/imports and checked source custody.

The separate full-store execution and paired-update suites validate the complete
selected cohort and exact packaged bytes. No host simulation executes Xtensa
instructions, measures power/current, verifies RF reception or substitutes for
physical sleep/wake testing. Those remain checks for the owner's new-device test.
