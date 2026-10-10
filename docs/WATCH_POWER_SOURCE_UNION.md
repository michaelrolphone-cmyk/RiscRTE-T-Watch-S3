# Watch power and serial recovery reconciliation

## Result

No new production sleep, one-shot low-battery, or active-capture idle defect was reproduced. Completed fixes are preserved and freshly checked. The new script selects one canonical SDK for a recovered Watch/current-System diagnostic build; it does not change a product profile, behavior, version, charging policy, or delivered image.

## Exact source selection

- Recovered Watch source: local `a5dae2bd17945d7927f3758e5f8714111f45daab`. This is the full recovered saved-files 1.0.27 source, not a claim that it is the latest complete Watch union or a published equivalent of the new test branch.
- Current System: public `8a75862929e4e83c8f66b3d58cc1c36d44830c84`, local `bd98b2e14c8d4ac20e4075c03396b12d8480e8f4`, tree `2a2de2b8b7537a3bfd322a6c4771f28e51e774df`.
- Runtime 0.2.3: public `67e0dbe1a5f519fd96d8f88797ff91b9e1a3096c`, local `b7c5becf9cd2eca902638d4f99cf3bb1f3394ddb`. Later capacity/HCI work is separate and must be reconciled by its owner.
- Alarm source/header: public Utilities `e80172353fcb9e6519ca9d9b2a4d43c69c1bc91d`, `lib/Alarm/include/AlarmServiceV1.h`, including the completed sleep-resume suffix.

The accepted corrected Watch touch 0.2.1 remains a separate required input from recovered Watch tooling source `5b9fd5735034e5c7d7731417d9664f4171b3b04a`, `drivers/current/twatch_touch`. The recovered 1.0.27 root still carries old 0.2.0; do not accidentally select it when composing the next complete Watch. This power unit does not edit or select the separate 0.2.2 touch candidate.

## Canonical header recipe

Run `scripts/test_selected_power_union.py --watch WATCH --system SYSTEM --runtime RUNTIME --alarm-source ALARM_SOURCE --output ABSENT_DIRECTORY`.

The script copies the selected System PortableApps include tree into a fresh SDK, overlays only the explicitly supplied alarm sleep header, and verifies that Runtime and KeyValue headers equal the selected Runtime. It includes the canonical current sleep policy first, then defines the legacy Watch guard to suppress the second local copy. New profile APIs remain available. Original Watch/System source is untouched. The alarm-enabled local sleep fixture thus sees the actual completed resume suffix rather than the older System header.

For a future target recipe, use that staged SDK before legacy Watch include paths and `-include sdk/WatchSelectedSleepPolicy.h`. Preserve every existing Clock feature define and required source unit. This binding is explicit; historical frozen builders keep their existing source pins and header-equality checks. Do not bypass those checks and relabel a mixed-source build as a historical artifact.

## Fresh software evidence

- Ten selected-header programs pass: alarm on/off crossed with low-battery timers on/off, plus actual Clock crossings/manual controls/reboot/charging/unknown battery/configured Hybrid timer; each runs normal and ASan/UBSan.
- The full-feature recovered Clock translation unit compiles with the selected canonical SDK using official GCC 8.4, preserving launcher, quick controls/radios, motion wake, alarm resume, Points, low-battery and boot-confirmation defines. A second compile also retains Runtime-feature, BLE-broadcast and Contexts-client defines. This is a compile-closure check, not a final linked/cohort-admitted Clock ELF.
- Unchanged Watch PMU cold-boot/retry/restore, charger status, both IMU preparation/rollback fault matrices, Hybrid policy and terminal Deep app lifecycle suites pass. Fresh target provider compilation and structural/import gates pass. Power targets remain PMU 0.6.2, IMU 0.4.2 and panel 0.4.2. Other outputs from the existing all-provider builder are qualification byproducts, not proposed next-product inputs.
- Current Runtime diagnostic/journal and real pinned Arduino 2.0.17 HWCDC recovery tests pass normal and ASan/UBSan; CPU Light cleanup and terminal Deep/fresh-process wake tests pass. Recovery is RAM-requested after successful native Light return, then owner-polled with bounded detach and no host wait. It remains enabled independently of optional retained recording. Rejected sleep does not force reconnect; retained wake cleanup remains retained.
- Independent bounded low-battery/capture audit passes 236 host executions: persisted edge/manual overrides, core policy, audio/radio capture lifecycle, combined crossing plus capture, actual Waterfall clean suspension and diagnostic Clock. These include duplicate Clock checks from the ten-program matrix and must not be added as a unique total.

## Remaining qualification and composition

No hardware sleep current, wake reliability, USB re-enumeration or terminal reopening was measured. Code cannot process serial while the CPU is asleep; the preserved mechanism restores transport after wake. It does not introduce a USB wake source or promise every host automatically reconnects.

The broad old Settings timer case 2 is already disclosed fixture debt and still fails its obsolete input fixture. The old Spectrum snapshot-only long-capture fixture never starts capture against the new input path; it is not counted as a wake-lock failure. LeakSanitizer is unavailable under the executor tracer; ASan/UBSan remain enabled.

A real next Watch increment still needs one explicit source union, fresh affected app versions, full app links, capability/grant/namespace graph and whole-product admission. The saved-files 1.0.27 recipe rebuilds Files only and preserves Clock; it is not proof that all current shared changes were compiled into Clock. Use the source pins and canonical binding above for that new composition, without substituting the historical Clock or qualification binaries.
