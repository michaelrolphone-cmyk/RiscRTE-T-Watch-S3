# Future Watch 1.0.7: automatic low battery

T044 is staged as a separate `watch-low-battery-apps-v1` source profile. It uses
Clock 0.10.3 and System Settings 1.3.1. Every rebuilt app receives a higher
**deployment** version in `apps/low-battery-sources.json`; unchanged upstream app
manifests retain their recorded `source_app_versions`. The shared adapter is
rebuilt into all 22 applications, including both Clock entry points.

The policy is automatic in this profile. There is no user-facing enable switch.
A valid reading below 10% applies 20-second idle sleep, 15% brightness, one-minute
Hybrid Light-to-Deep sleep, Wi-Fi off, and Bluetooth off once. The shared saved
edge prevents app switches, reboot, or repeated low readings from undoing later
manual changes. A valid 10% or higher reading rearms without restoring settings.
Charging alone and unknown/absent battery samples do not rearm it.

Clock and every portable application consume the same namespace-1 preferences.
The existing Settings mode choice is retained; the Deep Sleep Timer controls
Hybrid progression. Settings timer edits and Quick Controls brightness/radio
changes remain authoritative after entry. Existing radio-session cleanup and
alarm-resume boundaries are reused; no Runtime mechanism or driver ABI is added.

The System implementation documents bounded records and partial-write behavior
in `docs/PORTABLE_LOW_BATTERY.md`. The edge is committed before its multi-key
update, so power loss may leave a partial update. It is deliberately not replayed
on reboot. Unknown/corrupt state is reported, not repaired by erasing storage.

## Separate build and verification

The usual `current` build, `apps/current-apps-sources.json`, current Clock
manifest, Runtime requirements and all midpoint publication guards remain
unchanged. The accepted 1.0.6 payload remains pinned to its own source and ZIPs.
The optional build-profile selector preserves that artifact boundary; the new
profile always compiles the automatic policy into every application.

```
python scripts/build_current_apps.py --profile low-battery \
  --motion-model bma423 --radio-model selectable \
  --system-apps SYSTEM --utilities UTILITIES --productivity PRODUCTIVITY \
  --runtime RUNTIME --drivers DRIVERS --baseline AUDIO_BASELINE.zip \
  --output dist/low-battery-bma423
```

The paths must be clean checkouts of the exact new-profile pins. The target
compiler remains pinned Xtensa GCC 8.4. Builds verify the original baseline,
strict target ELFs/imports, source versions, capability grants, compaction proofs
and resulting archive contents. CI builds both motion variants. These are
app-cohort artifacts, not an installable native+boot-store pair or an authorized
release. Native integration/publication must use a separately verified future
upgrade route; never feed this profile into the frozen midpoint publisher.

Run production regressions with:

```
python SYSTEM/scripts/test_low_battery.py
python scripts/test_low_battery.py --system-apps SYSTEM
python scripts/test_alarm_sleep_resume.py --system-apps SYSTEM \
  --utilities UTILITIES --runtime RUNTIME
python -m unittest discover -s tests -p test_low_battery_profile.py -v
```

Coverage includes persisted crossings/manual overrides in the real Clock and
shared adapter, actual 20-second idle entry, the 60-second Hybrid boundary,
manual timer changes, alarm deadlines before/at/after that boundary, exact alarm
resume tickets, crown precedence, unknown battery, corrupt/unconfirmed storage,
radio cleanup failures, Settings rendering/navigation and normal/sanitizer runs.
Host/target checks do not qualify physical sleep current or device behavior.
