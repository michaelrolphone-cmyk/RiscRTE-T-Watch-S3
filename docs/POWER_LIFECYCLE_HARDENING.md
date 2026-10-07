# Power lifecycle rollback and retained-state hardening

This is a software-only correction to repeated sleep preparation and cleanup.
It does not change Light/Deep/Hybrid selection, alarm deadlines, low-battery
thresholds, charging policy, board wiring, or frozen release custody.

## Repaired failure states

- **PMU 0.6.2:** a failed awake-mask restoration used to leave `sleep_prepared`
  true after one or more IRQ masks had already changed. A second prepare then
  admitted native sleep without repeating the quiet-input checks. Restoration
  now invalidates preparation before its first write. The original IRQ snapshot
  and `sleep_changed` remain owned until all writes succeed; all ordinary,
  timed, and multi-source sleep entry points refuse meanwhile.
- **IMU 0.4.2:** failed rollback could leave `wake_prepared` true after sensor
  reset had cleared the feature image and interrupt map. Both BMA423 and BMA456H
  now invalidate preparation and live observation before rollback starts.
  Enrollment and sampled registers remain available for verified cleanup retry.
  Failed rollback cannot be mistaken for an armed detector or observation
  session, including when transport later recovers.
- **Panel 0.4.2:** partial resume could send SLPOUT successfully, then fail PWM
  or DISPON, leaving the old preparation proof true. Resume invalidates that
  proof before mutation, so Light/Deep rearming refuses until recovery completes.
- **Application cleanup:** the non-alarm sleep adapter now uses the typed panel
  restore suffix when available, preserving native retained-unhold results.
  Both Clock and the portable local adapter propagate retention in every build,
  including non-alarm builds. They do not free the saved image or release live
  display/PMU/RTC grants after native retention. Older panel prefixes retain
  their existing bool restore behavior.

## Deterministic before/after evidence

At pre-fix Watch head `273b58d64ccc9a7dd66f0659271a942f244edcdf`:

- Failing each of the three PMU resume writes after successful preparation left
  `sleep_prepared` true. Native Light entry returned OK with mask combinations
  `00/cf/5a`, `a5/08/5a`, or `a5/cf/00`, rather than the intended `00/08/00`.
- Failing IMU rollback transaction 6 after reset let a second prepare succeed
  with zero new transfers, while the sensor feature image and interrupt map
  were empty. This reproduced for both supported sensor models.
- A retained typed panel restore returned ordinary `WATCH_SLEEP_FAILED` from
  the non-alarm adapter because its typed callback was never called.
- The updated actual Clock fixture fails against the pre-fix Clock source at
  its forbidden post-retention capability-release assertion. The new portable
  fixture fails against the pre-fix adapter at its forbidden post-retention
  free assertion. The same fixtures pass with the repair.

## Host verification

Run from the Watch checkout, with the matching current System Apps sources:

```
python scripts/test_pmu_cold_boot_sleep.py
python scripts/test_pmu_charge_status.py
python scripts/test_motion_wake.py
python scripts/test_hybrid_sleep.py
python scripts/test_deep_sleep.py
python scripts/test_portable_sleep_lifecycle.py --system-apps /path/to/system-apps
```

The production PMU fixture injects each restore-write failure after a completed
preparation, retries admission three times, verifies rejection by all six native
sleep wrappers and the pending-query API, and then proves explicit cleanup and
fresh preparation recover. Charger enable, 100 mA limit, and thermal-policy
registers remain unchanged throughout these sleep and cleanup paths.

The production motion fixture injects all 25 rollback-transfer failures for
both chips, starting from both sleep and observation modes. It proves no
rearming/observation/setting changes or extra transfers after an incomplete
restore, then proves full cleanup, fresh preparation, and cleanup again.
Existing preparation, startup, retained-sensor Deep-reset and enrollment tests
remain active. Panel fixtures include failure after SLPOUT and before PWM,
repeated refused rearming, retry restoration, and retained hold/unhold behavior.

The application fixtures cover repeated Light/Deep/Hybrid results, short panel
ABIs, native retention, unexpected nonnegative Deep return, retained Deep
preparation and unhold, ordinary cleanup errors, crown-over-timer priority, exact
saved-image restoration, and retained image/grant ownership. The portable test
runs four ASan/UBSan builds: alarm on/off crossed with low-battery timers on/off.
Its allocator wrapper verifies ordinary free and retained ownership explicitly;
LeakSanitizer is disabled because it cannot run under the managed executor's
ptrace environment. AddressSanitizer and UndefinedBehaviorSanitizer stay enabled.
The existing low-battery CI job runs this new matrix using its pinned System
Apps checkout.

## Preservation and limits

Historical custody inputs, delivered archives, charging current, charger enable
policy, thermal settings, and the vendor sensor images are unchanged. New driver
versions identify changed current production bytes; they do not rewrite frozen
packages. Current-only source rebuilds remain subject to their existing version,
source-pin, package, and artifact checks.

These deterministic host tests establish software transitions and failure
handling, not physical wake reliability, battery life, charge termination,
electrical timing, or thermal safety. Target compilation is not device
qualification. No hardware access, flashing, merge, or release is part of this
verification.
