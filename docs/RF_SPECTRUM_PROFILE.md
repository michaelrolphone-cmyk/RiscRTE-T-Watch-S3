# Watch 1.0.8 RF spectrum candidate

The next full 22-app candidate uses the separate `watch-rf-spectrum-apps-v1`
profile. Waterfall source and deployment version are 0.2.0, and its IQ provider
is 0.2.0 at Drivers `4088b6892c2e2654b0342f04a7d191068e4a8e2e`. All rebuilt
apps receive a deployment version newer than accepted 1.0.7. The accepted
System, Productivity and Runtime 0.1.41 pins are retained. Automatic low battery,
alarm resume, Hybrid sleep, motion wake, touch corrections, HID and BLE sensor
providers are retained for the full cohort.

`apps/rf-spectrum-sources.json` pins the completed Utilities source
`39b8b0edd71bbf2831689aaa45077181eed5b27f`. The profile supports a null Utilities
commit while a source checkpoint is still incomplete; builds fail closed until
the completed clean source is pinned. The exact-pin helper is:

```sh
python scripts/pin_rf_spectrum_sources.py --utilities UTILITIES
```

The helper checks the actual clean checkout, accepted Utilities ancestry, all
upstream utility app versions, and the RF manifest. It writes only the new
profile and reads it back through the normal validator. A populated pin cannot
be silently replaced with a different commit. Review and commit that pin before
building; the caller remains responsible for approving final source readiness.

## Candidate build

```sh
python scripts/build_rf_spectrum_apps.py \
  --motion-model bma423 --radio-model selectable \
  --system-apps SYSTEM --utilities UTILITIES --productivity PRODUCTIVITY \
  --runtime RUNTIME --drivers DRIVERS --baseline AUDIO_BASELINE.zip \
  --output dist/rf-spectrum-bma423
```

This candidate command defaults to RF spectrum. The historical shared builder
retains its default; it also accepts explicit `--profile rf-spectrum`. Build
both supported motion variants before integration. Source checkouts must match
the immutable profile pins and use the existing pinned Xtensa GCC 8.4 compiler.
The archive contains all 22 apps, all existing providers, debug ELF custody,
licenses and exact source/Runtime/storage proofs. Waterfall links System
`SingleFloatDivisionCompat.c`; its transitive target dependencies are recorded
and checked to exclude host fixtures. The RF app owns nested Back and root
launch through `RF_RETURN_APP="springboard.elf"`.

## Storage and migration

Waterfall keeps shared radio/settings preferences in KV API1 namespace1. RF
labels, rooms, signatures and settings use KV API2 namespace13. RF event banks
and neural checkpoint use app-data API1 namespace3, separate from audio
Spectrum namespace2 and Timecard namespace1. The three RF files require
129004 bytes of the existing 131072-byte namespace quota.

The six source requirements plus mandatory deployment battery, shared KV1,
RTC2, Wi-Fi1, HCI1 and motion1 produce exactly 12 requirements and 12 grants.
Optional source navigation uses the existing Watch local navigation adapter;
it does not consume a thirteenth native grant.
No Runtime capacity or ABI change is needed. Every accepted grant and provider
storage binding remains unchanged; only the two previously unused RF private
grants are added.

The accepted boot policy contains an old 1.0.4-to-1.0.7 HID shared-KV migration.
The 1.0.8 candidate omits that record. Retaining or merely retargeting it rejects
the accepted 1.0.7-to-1.0.8 transition. No new shared namespace authority is
needed for the private RF namespaces. The production Runtime regression checks
the accepted store, this transition, candidate self-admission, namespace theft,
removing existing preferences, missing requirements and a thirteenth grant.

```sh
python -m unittest discover -s tests -p test_rf_spectrum_profile.py -v
python scripts/test_rf_profile_runtime.py --runtime RUNTIME
SANITIZE=1 python scripts/test_rf_profile_runtime.py --runtime RUNTIME
python -m unittest discover -s tests -p test_complete_watch_release.py -v
```

The Runtime test reuses accepted target ELFs with candidate metadata to isolate
production policy admission. It does not qualify the new RF ELF or device
behavior. Both complete target cohorts, strict ELF admission of those cohorts,
capacity/packing checks and a separately verified 1.0.7-to-1.0.8 update package
remain required before publication. This work creates no full images or release
and changes none of the accepted 1.0.7 or frozen 1.0.6 publication inputs.
