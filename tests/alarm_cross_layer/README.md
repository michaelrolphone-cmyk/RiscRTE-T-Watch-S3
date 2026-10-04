# Watch alarm/native hold cross-layer regression

Run from the Watch checkout:

    python /tmp/watch-alarm-cross-layer/run.py --watch . --runtime ../runtime-exact --utilities ../utilities --system-apps ../system-apps
    SANITIZE=1 ASAN_OPTIONS=detect_leaks=0 python /tmp/watch-alarm-cross-layer/run.py --watch . --runtime ../runtime-exact --utilities ../utilities --system-apps ../system-apps

The fixture compiles the unmodified Utilities alarm service into a shared ELF and exercises the production Watch watch_alarm_sleep.h with real Runtime, ProviderGraphV2, ProviderModuleV2, dynamic app lifecycle and CpuPort native GPIO hold/sleep machinery. Only physical hardware, backing key-value storage, RTC/output dependencies, and the panel/PMU delegation shell are modeled. The panel/PMU shell calls actual CpuPort owned GPIO APIs, including actual hold, unhold and timed sleep. This is not a physical qualification and does not replace production panel or full Clock/shared-app caller tests.

Cases:
- old-order: actual service step after successful native hold receives ALARM_STORAGE without reaching backing storage; even after unhold, refresh/step remain blocked because real Runtime revoked provider KV.
- direct-refusal and hybrid-refusal: production helper performs real service reconciliation/KV/RTC before hold; no service callback, RTC read or KV backend call occurs while held; ordinary refusal restores first and later service KV remains live.
- crown-after-hold: crown wins the final boundary; native deep entry is never called, hold is restored and service authority remains live.
- native-return: backend unexpected deep return is classified native-retained and production helper returns -2; real Runtime skips app fini and provider quiesce.
- unhold-retained: failed native unhold has the same retention behavior.
- resume-spi-error: successful unhold followed by ordinary modeled panel SPI restore failure remains generic -1; provider KV remains live and Runtime permits normal teardown, proving signed restore distinction.

Each scenario runs in its own process. Retained scenarios deliberately exit without C++ destructor cleanup to preserve the lifecycle evidence. Host test does not prove Xtensa heap reclamation; production caller tests separately cover retained saved-frame/grant behavior. The build stages Watch-only missing SDK headers, then uses Runtime's canonical SDK headers to avoid duplicate pragma-once header definitions.
