# Hybrid and alarm RTC boundary investigation

The installed image `twatch-s3-tap-midpoint-27fba6f2.bin` is confirmed by SHA-256
`2225261601729774c7d0d42a88ab1a705c55aa856097af292dce9fa06dd659bf`.
It contains Clock 0.10.1, IMU 0.3.6 and Runtime 0.1.33 at `e08609b4`.
The report concerns the five-minute Light-to-Deep boundary and an RTC error when
an alarm becomes due. This is separate from the lazy IMU startup-reset fix.

## Reproduced error propagation

After a successful five-minute Light timer return, the prior Hybrid adapter
discarded failure of its second alarm reconciliation. It retained the native
Light success result, skipped Deep, restored the panel and reported a normal
wake. Its deadline helper additionally collapsed a blocked service's actual
error into generic BUSY. A valid due alarm and a failed RTC/storage read were
therefore indistinguishable in this branch.

The correction preserves the blocked service's error, distinguishes it from a
real due/owned alarm, returns a refusal with the ALARM diagnostic stage, and
avoids an automatic refresh that could erase that error. Due alarms still wake
normally. Panel/PMU/motion rollback and retained-resource barriers are unchanged.
Focused normal and ASan/UBSan adapter/Clock/retained-app checks pass. A physical
freeze is not reproduced by this error-propagation test.

## Independent clocks across Light sleep

The exact service also rejects an absolute difference greater than two seconds
between external RTC elapsed time and the platform monotonic clock. That anchor
currently survives Light sleep. Independent-clock host cases reproduce an RTC
error after valid +303/+300 or +300/+303 second advances; ordinary awake time
edits remain correctly rejected. The direct timed-alarm wake and Hybrid
reconciliation paths expose this differently because of their refresh order.

The pinned IDF 4.4.7 implementation advances `esp_timer` after Light sleep using
an estimate from its RTC slow clock. This build selects the internal RC source;
the Watch calendar comes from a separate PCF8563. The two clocks are not an
identical sleep-time reference. Actual disagreement on the user's device has
not been measured, so this mechanism is not asserted as complete physical
attribution of the reported freeze.

- [IDF 4.4.7 sleep compensation](https://github.com/espressif/esp-idf/blob/v4.4.7/components/esp_hw_support/sleep_modes.c#L694-L810)
- [IDF RTC source and sleep-time drift](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32s3/api-reference/system/system_time.html#rtc-clock-source)

## Explicit successful-Light resume boundary

Utilities alarm-service 0.4.2 adds an optional `alarm_service_sleep_v1` wrapper.
The original 36-byte target table remains unchanged, and the wrapper appends a
single callback at byte 36 (40 bytes total). System carries the byte-identical
header from Utilities `e6444bb4`; existing prefix consumers remain compatible.

A successful `prepare_sleep` produces a one-use copied decision. Only after the
native Light call returns OK does the current Watch adapter pass that unchanged
decision to `resume_sleep`, before any service step/refresh or Deep pad hold.
The service validates the ticket, one fresh calendar, backward RTC and monotonic
time, then reanchors the independent clocks and begins full reconciliation.
Wrong/reused decisions, invalid/backward clocks and ordinary native refusal do
not authorize reanchoring. The existing awake two-second change checks remain.

The new current-cohort compile flag requires this suffix explicitly. Old-prefix
providers refuse that current sleep path before peripheral preparation; frozen
historical builds retain their original prefix path. The current source profile
and actual-store host execution both require the flag, preventing tests from
silently exercising the old path while target applications use the new one.

`test_alarm_sleep_resume.py` compiles the real provider and Watch adapter with
independent clocks. Both drift directions now reach the Hybrid Deep decision or
deliver the due alarm; an alarm becoming due across the five-minute boundary wins
over Deep. Real storage/RTC failures remain visible, and native refusal still
preserves awake clock-edit rejection. Normal and ASan/UBSan runs pass. The exact
installed helper fails the same combined regression. Original API consumers,
Clock/retained-app alarm behavior and Points cues have separate regression gates.

This is software evidence, not measured hardware drift or proof of every reported
freeze. No release, catalog advancement or device installation is implied. The
installed midpoint source also needs its own bounded migration profile; it must
not be substituted into the frozen released-1.0.2 upgrade proofs by name alone.
