# Clock-first wake checkpoint

This source is an explicit `WATCH_FAST_WAKE` opt-in. Existing product builders
and the delivered 1.1.11 image are unchanged. No hardware timing is qualified.

## Exact source custody

The delivered 1.1.10/1.1.11 default is Clock 0.11.2, preserved from the decoded
1.1.5 store. `build_watch_crown_recovery.py` deliberately does not rebuild it.
Its original command and 98 dependency hashes are in
`docs/watch-110-touch-buttons/delivery/clock-reproduction.json`.

- System: `63532e4611749acad2060d0437a883b7c4ac8fd5`
- Utilities: `814502e51125d799a7ca625b78707753ca12d4e5`
- Product base: `058adc7c9567bd0cb47dc4b04f3d8e8935096b3a`
- Delivered default SHA-256:
  `0470fd3fe48e144a6c0da45ee967b8808eff6dd321d39b0d10c2d193aebd16d2`

Use `scripts/build_watch_fast_wake_clock.py` with those System/Utilities sources
and the verified complete delivered store. It checks the exact dependency
closure, reproduces the original default byte-for-byte without the opt-in,
then builds the selected fast Clock 0.11.3. It produces only an ELF, manifest
and receipt. `clock.elf` is the existing return-to-default wrapper and stays
unchanged. Files 1.5.30, other applications, manifests, providers, grants and
cohort are untouched by this builder. Successor image assembly is separate.

## Source-visible bottlenecks and change

The original successful light wake calls `startup`: 1,800 ms of intro,
250 ms holding its completed final frame, then a 180 ms blur/blend. Those are
application clock budgets, not measurements of a physical Watch. Cold/deep
entry also acquires broadcast and Contexts and applies radio policy before the
first Clock frame. Deep wake avoids the intro only with a valid checkpoint.

The opt-in removes intro work from initial Clock entry and light wake. The first
frame still uses the selected face, time format, brightness, native/RTC time
policy, Points configuration and alarm reconciliation. Due alarm UI remains
higher priority. It drains the accepted frame before enabling the backlight.
No app buffer or frame lease survives sleep or handoff.

After the first frame, each settled foreground turn handles crown/touch and
renders before admitting at most one startup phase:

1. Existing saved Wi-Fi/Bluetooth policy
2. Broadcast client and first/resumed service step
3. Contexts client, pause/export recovery and first/resumed service step
4. Existing provider promotion and paired-boot confirmation

Radio controls remain unavailable until policy loads, including after light
wake. Broadcast and Contexts cannot resume before their explicit phase after
wake radio policy is restored. A swipe latched during presentation bypasses
deferred work; a Contexts launch queued during admission returns immediately.
Low-battery crossings queue radio application through the same phased path. Sleep still pauses background
services and proves Bluetooth suspension; light wake presents first, then
restores radio policy. All cleanup/retention paths remain checked. Pair
confirmation is deferred until all original startup services have been admitted;
a visible frame by itself never confirms a pending native/store pair.

A phase's provider calls are still synchronous. The app cannot preempt a slow
native/provider start while inside that call. This change creates input and
presentation opportunities between phases; it does not claim that service
activation is hardware-nonblocking.

## Measurement

Fixed `WATCH_WAKE` diagnostic records include boot-local `t_ms` and unsigned
`elapsed_ms` from Clock entry or light-resume return. Separate records identify
`first-frame`, `first-input-poll`, each deferred phase, and `services-ready`.
Light wake additionally records `light-resume` and `light-frame`. These do not
measure the crown edge, ROM/bootloader, or panel photons. Native stage logs can
identify pre-application boot work in a separately selected diagnostic build.

`scripts/test_fast_wake_clock.py` compiles the actual Clock and renderer, with
mocked hardware/API boundaries. It passes normal and ASan/UBSan (LeakSanitizer
disabled). It covers all five boot causes with checkpoint present/absent, due
alarm, explicit unset time, asynchronous frame failure, deferred admission
failure, early launcher handoff before deferred work, saved face/24-hour/brightness,
production Points/motion/alarm-resume paths, early/repeated light wakes, cold
and resumed low-battery crossings, radio policy/failure variants, and failed
Context/Broadcast cleanup retention. The fixture fences I/O after retention
and enforces input polling and distinct frames between service-start phases.

The deliberately modeled scenario assigns 95 ms to each display transfer and
700 ms to each of four service acquisitions plus 400 ms to each service start.
First visible Clock and first
input poll occur at 95 ms, ahead of those service costs. Each modeled light
resume frame takes 95 ms. Neither number is a physical Watch measurement.

```sh
python3 scripts/test_fast_wake_clock.py --system-apps /path/to/exact-system \
  --utilities /path/to/exact-utilities
NATIVE_APP_CC=/path/to/xtensa-esp32s3-elf-gcc \
  python3 scripts/build_watch_fast_wake_clock.py \
  --system /path/to/exact-system --utilities /path/to/exact-utilities \
  --baseline /path/to/verified-delivered-store --output /new/output
```
