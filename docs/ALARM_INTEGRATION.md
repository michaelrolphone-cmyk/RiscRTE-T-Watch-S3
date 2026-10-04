# Explicit low-power Alarm / Countdown development integration

This separate nine-app deployment selects the original Utilities singleton
alarm-service0.1.0. No firmware scheduler, board-local schedule copy, recurrence
or snooze policy is introduced. Clock0.6.5 incorporates independently reviewed
picker0.6.4, including all24 faces, cyclic category motion, focused caching and
persisted12/24-hour display choice. Stable product1.0.0 and its release descriptors remain immutable.

The explicit physical closure is GPIO1, I2C2, touch-I2C3, PMU4, panel5, touch6,
RTC8, haptic9 and speaker12. PMU configuration keeps only display rails1/2 and
haptic rail5, all at their already declared3300mV. No radio, microphone, IMU or
USB application is added. The service is an ordinary software singleton, without
a fabricated hardware instance. Its five-key map is namespace3 read alarm_cfg /
timer_cfg; namespace4 read-write alarm_occ / timer_occ; namespace1 read alert_mode.
No application receives namespace4 or an output/provider-KV capability.

Nine applications receive only alarm.service in addition to their prior explicit
grants: default Clock, return Clock, Springboard, Battery, Settings, Calculator,
Stopwatch, Alarms, Countdown. Writers alone receive namespace3. Settings and Clock
retain existing namespace1 scope; Stopwatch retains namespace2. Runtime0.1.8
supplies the reviewed generic capacity16 and native I2S cleanup prerequisite.

The shared adapter keeps each app's stack, model and completed frame during an
alert. Clock keeps the selected global face ID, category/axis positions and its
six-card picker allocation in its own invocation. An opening queued inside a
pending frame is cancelled before it becomes visible; alert-dismissal contact
and queued selection/launcher actions are suppressed. Every normal service
phase runs at an explicit settled display point before Back, gesture, app switch,
or sleep decisions. Pending/failed presentations run only bounded independent
stop_only cleanup; uncertain cleanup retains the invocation and grants with no
further foreground/service I/O; Runtime provider polling retains its yield contract. Exact-current dismissal is not complete before safe output stop and
durable service reconciliation. New due occurrences stay in the alert view.
Dismissal starts a fresh60-second inactivity interval, so even a long alert
returns to a visible retained picker before Clock can sleep again.

Clock handles due work before fresh-boot or Light-wake intro. Owned Light/Deep
entry consumes a fresh prepare_sleep decision on the same serialized task. The
runtime sees only a bounded duration, not dates or alarm policy. Longer-than-day
waits are bounded to the canonical one-day native timer maximum and rechecked on
fresh boot. Hybrid Light-to-Deep reconciles again at its timer boundary; a crown
wake wins. Refusal/return refreshes the snapshot. Ordinary apps use the same
alarm-aware owned sleep helper and restore their exact frame and live stack.

GPIO0.4.2 and PMU0.5.2 add the canonical timed-Deep delegation and an
append-only PMU callback. Old prefix sizes/offsets and untimed sleep behavior stay
unchanged. Panel0.4.1 adds a signed resume-status suffix to distinguish ordinary
SPI restore failure from native retained unhold while preserving bool resume.
The120ms ordinary panel preparation happens before service reconciliation, then
Deep establishes pad hold and immediately checks crown/enters without any further
service/storage call. Native-retained results propagate through Clock/shared
callers directly to Runtime before any app cleanup or provider poll.
Unsupported short tables refuse; negative entry statuses propagate;
retained native state never executes restore I/O. Board baseline is1.1.3.

## Common store and development image

The alarm-specific common builder verifies all eight profile archives, then
normalizes only board.revision after their selected stores compare byte-for-byte.
It retains enough provenance to reconstruct every original archive. The38-file
store has nine app policies and the same explicit five-key service mapping.
The SPIFFS builder uses pinned mkspiffs2.230.0 and unpacks its result to verify
every file against that common archive.

The development-image builder requires a clean reviewed Watch tree, a successful
exact-head CI artifact receipt, and the exact Runtime0.1.8 16MiB-target components.
It verifies the image headers, partition table, firmware version and source
identity, service and driver payloads, and the final store. The merged image is
8MiB at offset0 on16MiB hardware using the existing layout. Its NVS region is
erased: writing that complete image resets saved settings, alarms and timers.
Build/verification never opens a serial port or flashes a device.

## Validation boundary

Host fixtures and pinned GCC8.4 target ABI/import checks are software evidence,
not physical qualification. Required checks include actual shared app models,
Clock boot/wake/retention/input paths, service invalid-RTC/cancel/storage retry,
output cleanup while display pending, nine-policy exact authority, real dynamic
loader and final exact-head CI/artifact provenance. Physical wake reliability,
output level, shutdown, persistent power-loss behavior and current draw remain
unverified until separately authorized hardware testing. This source work does
not merge, release or flash a Watch image.
