# Retained T-Watch 1.1.46 power-controls qualification

This additive qualification does not change the released product, production
recipe, source pins, grants, acceptance baseline or any app/provider/native bytes.
It does not select the separate Settings 1.4.2-dev1 or release a new firmware.

The subject is producer `ab9ff33975680c5bb8d9a2e7ed346d0300732a4e` and its
[public 1.1.46 release](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/releases/tag/test-provisioning-1.1.46).
Exact release CI [39026555734](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/actions/runs/39026555734)
passed native/store admission for all 61 ELFs, including the byte-retained Settings
1.3.25. It did not execute those Xtensa apps or test hardware.

## Bounded scope

1. Independently download the public store, native evidence, source lock and CI
   provenance; verify pinned lengths and hashes before using them.
2. Decode the actual 125-file store, retain Settings `fa1c87a1…` (142164 bytes),
   Home `f376d722…` (554744 bytes), app namespace-1/power/display/input grants and
   provider bindings. Check every unchanged baseline file.
3. Recompute linked Runtime/workspace placement from the actual released native
   ELF and verify every locked native input. Static memory evidence is not live
   heap availability or a measured application/provider allocation peak.
4. Reconcile the exact retained Settings producer and selected flags, then test
   its actual mode/timer Save/readback and Home consumer paths without replacing
   production logic with a duplicate model. Preserve any unresolved boundary.
5. Add rejection controls for changed artifacts, sources and capability bindings.

Artifact validation, historical-source checks and current selected-boundary
suites are separate gates. Their results must not be combined into a claim of
physical acceptance or a bit-identical historical Settings rebuild.

## Installation and physical boundary

The published factory image is a destructive offset-zero installation. It erases
existing saved data. No preserving update kit is established. Native firmware and
store must remain paired; no device or radio action is part of this work.

Physical sleep/wake, display/input restoration, current consumption and live
memory fit remain untested. A host fixture or successful ELF admission does not
close those boundaries.

## Reproduction

Use Python 3 with pyelftools 0.32 and a clean checkout of the exact product
producer. Run `python tests/retained_power/qualify.py --product /path/to/producer
--assets /path/to/cache --output /path/to/report.json`. The cache is rehashed on
every run. The qualification workflow has read-only contents permission, no
publishing job, no hardware tool and no production build step.

## Historical producer and selected consumer

The T054 [source pins](../t054/source-pins.json),
[recorded Settings command](../t054/settings-command.json),
[build recipe](../../scripts/t054/build_apps.py), and
[assembly](../../scripts/t054/assemble.py) identify System
`9dcb2bbef44853e533d980a658a814d2c787a4fa`. The command enables
`PORTABLE_SLEEP_SETTINGS`, `PORTABLE_LOW_BATTERY`, tap Settings, rotation 0 and
local navigation/sleep; it does not enable atomic key-value access. The command's
version macro is 1.3.24; assembly increments the manifest to 1.3.25. The artifact
report records every enabled `-D` argument instead of substituting a newer profile.

The shared bridge provenance points to Watch
`6e82fdcaec0b73ed700d2104cfb4d94f011c19d4` in the historical System
[reproduction record](https://github.com/michaelrolphone-cmyk/RiscRTE-System-Apps/blob/9dcb2bbef44853e533d980a658a814d2c787a4fa/docs/t054/public-reproduction.json).
That record includes different output profiles and dirty source metadata. It is
**not** a clean, bit-for-bit reproduction receipt for retained `fa1c87a1…`.
This qualification establishes documented lineage and actual retained bytes,
not a newly proven complete source-to-byte rebuild. Current System `bb0cadf…`
builds Home; it must not be mislabeled as the retained Settings producer.

`source_checks.py` compiles the historical Settings controller and original
policy tests without editing production source. It also compiles independent
historical-producer and selected-Home-wrapper executables and passes the actual
serialized records between them. It is not a Python reimplementation of policy.
The source-only suites are not a full production-flag replay or execution of the
retained Xtensa apps. The exact original fixtures cover mode Save/Cancel,
readback, invalid/missing records and failure paths, and low-battery/timer UI.

A specific persisted-record boundary is checked explicitly: historical policy
accepts 0 (Off), 3601 seconds and 14400 seconds; selected Home rejects them and
falls back to 60 seconds idle / 300 seconds deep. These are not ordinary editor
choices. The retained UI edits idle in 5-second steps (5–3600 seconds) and deep in
60-second steps (60–3600 seconds), with no explicit Off choice. Those 780 bounded
choices are exchanged and checked in normal and ASan/UBSan builds. Preserving the
six inherited-record differences is an expected qualification result, not a
claim that those records now work or that ordinary controls are defective.

## Shared capabilities and custody

Actual boot grants bind both apps to namespace 1 through `storage.key-value@1`.
Settings writes `sleep_mode`, `sleep_idle`, and `sleep_deep`; Home consumes the
opaque application records. Runtime owns authorization/NVS persistence, not the
policy meanings. Retained Settings uses synchronous key-value operations backed by native NVS.
Selected Home independently enables WATCH_ATOMIC_PREFERENCES and
PORTABLE_QUICK_ATOMIC_PREFERENCES in its canonical build receipt; its Runtime
preference operations must not be inferred from the older Settings profile.

Both apps receive `power.sleep@1:0`, `display.power@1:0` and
`input.power-key@1:0`. The retained power bridge requires `board.battery@1` and
forwards available light/deep/timed/wake-set callbacks from PMU instance 4,
through GPIO instance 1 and Runtime CpuPort to native ESP-IDF sleep functions.
The display-power bridge requires `display.output@1` and forwards panel
prepare/resume. Optional callbacks are not invented by the bridge. Original
bridge tests exercise three roles, including absent callbacks. The released
native ELF is independently checked for the sleep/custody implementation symbols.
Presence is link evidence, not proof of executing the selected tables on hardware.

The exact Watch source's original 56-case Runtime-sleep suite exercises production
Home prepare/refusal/resume/retained-custody paths. Original exact Runtime suites
exercise Light, Deep, timed/wake-set, lifecycle and NVS boundaries using host
shims; they do not prove physical device behavior. Leak detection is explicitly
disabled; ASan/UBSan are enabled wherever the original runners support them.

## Durable evidence

The workflow's JSON/log uploads expire after 30 days. They are transport, not the
permanent acceptance record. Terminal run IDs, commit IDs, result summaries and
receipt hashes are committed separately after CI verification. No local result
or unpublished commit is represented as GitHub qualification.

## Verified d3829b6 checkpoint

Qualification [PR CI39704855594](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/actions/runs/39704855594)
and push CI39704851220 passed at `d3829b66d79d726e70bb4f1ea49980f0ff879dac`.
[Permanent receipts and exact CI ZIPs](evidence/d3829b6/) preserve the downloaded,
rehashed evidence independently of Actions retention. This checkpoint is kept
separately from subsequent full-feature fixture work.

The 780-value matrices are **header record exchange**, not UI event traces or
Home scheduling tests. The original 56-case Home runtime-sleep suite does not
enable PORTABLE_LOW_BATTERY, so it does not exercise quick_session timer loads.
The original Settings mode fixture likewise omits other retained feature flags.
Historical 190-case native-height evidence omits LOW_BATTERY and TAP together,
and does not close that combined-feature boundary. Dedicated additive
feature-faithful fixtures are in progress; this checkpoint does not claim them.

## Full-feature source fixtures

`settings_profile.py` replays all 25 recorded Settings feature definitions and
both forced includes using the documented System9dcb / Watch6e82 producer.
It exercises real navigation/controller Save, Cancel, no-op, write failure,
commit-with-error, failed readback and reopen/displayed values: 21 cases each in
plain and ASan/UBSan builds. Its three actual UI-saved profiles contain all three
modes, 65-second idle and 360-second deep timers. Timer readback can confirm a
write whose provider returned IO; the mode path conservatively reports that
same error as unconfirmed. This fixture preserves that historical distinction.

`home_profile.py` separately reads Home's exact feature definitions from the
hash-locked release receipt, including canonical crash namespace61, LOW_BATTERY,
Runtime preferences and both atomic-preference flags. It executes selected
`crown.c`, `quick_session.c` and the real sleep helpers with opaque Settings-saved
records. For each mode it checks valid, missing, corrupt, wrongly namespaced,
read-IO and acquisition-denied cases. The mock asserts actual shared namespace1
access; records stored in namespace2 are not visible. Six additional historical
Off/out-of-range records come from the separately compiled producer helper,
not UI actions. Those records exercise the actual Home fallback/scheduling path.
There are 24 cases per plain/ASan-UBSan build, not a 780-case UI/scheduler matrix.

The clock is synthetic: the fixture checks no sleep request immediately before
the idle deadline, then observes actual Home dispatch and propagation of the
deep timer into the light-then-deep request. Deep callbacks return a modeled
platform refusal to permit cleanup; no terminal deep entry is simulated.
Persistent namespace1 acquisition denial loads default timers but subsequently
refuses at motion preflight, after paired Runtime prepare/resume and before
native sleep requests. Read failure under an acquired grant is a distinct case.

The enabled `storage.preferences` facade is acquired, revision-checked and read
by Home's healthy-battery path. Its mock advertises the selected Runtime's
COPIED_INPUT-only flags. Timer reads themselves still use namespace1 generic
KV. No Quick modal transaction, native atomic-group durability or physical NVS
persistence is inferred from this fixture. Existing exact Runtime/NVS boundary
suites remain separate evidence.

Both host runners reject wrong source/provenance inputs and missing timer
feature flags. Host compiler/ABI replaces target Xtensa options; full feature
replay does not close the dirty historical source-to-retained-ELF reproduction
gap. Optional devices/services are mocked, not target-qualified. Final CI
receipts are published only after exact-head verification.
