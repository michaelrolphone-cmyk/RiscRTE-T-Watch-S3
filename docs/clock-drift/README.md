# Hardware RTC reconciliation after wake

The selected morning Clock skipped acquiring rtc.clock on valid deep wake, and
watch_runtime_seed also returned before reading hardware RTC. Native VALID
indicates retained state, not external-RTC accuracy. Injecting native time five
minutes ahead or behind reproduces the divergence in the actual Clock fixture.
The size or cause of physical oscillator drift has not been measured.

Clock now uses the existing fast first-frame/input path, then acquires its RTC
immediately after alarm activation and reconciles native time. The alarm closure
already depends on the RTC. Light wake repeats reconciliation after first input.
The next rendered frame samples corrected time. No hardware RTC writes, alarm
changes, Points content changes, timezone changes, or native firmware changes.
A provisional first frame can briefly show the retained native value.

Validation: production Clock with actual Points/motion/alarm-resume feature
paths in normal and ASan/UBSan builds; six ahead/behind deep-wake regressions;
repeated light wake; all existing fast-wake/custody/alarm/refusal cases.
333563 RTC/Denver civil conversions passed normally and with ASan/UBSan.
The modeled first Clock frame/input remains 95 ms. This is not hardware timing.
The old combined runtime host runner cannot link recent Runtime stream features;
that unrelated runtime integration was not qualified by this patch.

Ordinary optional RTC acquire/read refusal keeps Home responsive only after a
fresh native read confirms VALID live authority. It shows TIME CHECK ERR and a
failure diagnostic, with retry on the next wake. Native CONTEXT or malformed
nonempty failed-acquire output preserves the retained fence. Three actual-app
failure cases verify ordinary acquire/read refusal and retained RTC failure.
