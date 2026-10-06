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

A narrowly scoped, one-use service resume boundary is in progress. It will
reanchor independent clocks only after successful native Light sleep, validate
a fresh calendar and reject backward RTC/monotonic time, while retaining the
existing awake time-edit checks. Until that integration is verified, this
checkpoint is only the error-propagation correction. No physical qualification,
release, catalog advancement or device installation is implied.
