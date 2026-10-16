# Watch declarative Alarms prototype 0.1.0

This opt-in selection uses Alarms 0.3.0, the shared optional scene host, an external compact-color presentation profile, and raw-RTC alarm control. The application ELF is identical to the X4 selection. Device layout, touch geometry, fonts and color decisions are outside that ELF.

`sources.json` pins the tested shared component sources. These are component pins, not replacements for the current native product source lock. The existing default firmware, deployment cohort, saved alarm/countdown/Points data and legacy Alarms selection are unchanged by this commit.

## Build a component stage

Check out the three source pins into sibling directories named Runtime, System and Utilities. With the pinned Xtensa compiler installed:

```sh
python System/scripts/build_scene_services.py --runtime Runtime --output build/scene-system
python Utilities/scripts/build_alarms_scene.py --runtime Runtime --system-apps System --output build/scene-alarms
python Utilities/scripts/compose_alarms_scene.py \
  --store "$CURRENT_WATCH_STORE" \
  --system-packages build/scene-system \
  --alarm-packages build/scene-alarms \
  --profile Watch/prototypes/alarms-scene/profile.json \
  --runtime Runtime --output build/watch-scene-stage
```

The script copies the store, replaces only Alarms and its grants, adds the three optional providers, checks scheduler/storage bindings and namespace 61 availability, and preserves unrelated package bytes. It removes obsolete cohort metadata rather than misrepresenting the old cohort as covering the new selection.

The current Watch selection has 24 providers; the prototype has 27. Its current native candidate needs the generic provider-capacity support at 28 providers/44 grants in PSRAM metadata. A linked native witness can be checked by adding `--native-elf "$NEW_NATIVE_ELF"`; build-flag text alone is not proof. A component stage remains non-flashable until bound into a newly generated product-native cohort/image.

## Verification boundary

Shared tests execute the real Runtime, scene host, Alarms controller, domain provider, scheduler and file storage with hardware doubles. They prove actual controller unload/reload, draft restoration, exact-command save recovery, and alarm firing after the GUI has unloaded. Presenter tests cover compact-color and rotated monochrome, including pending refresh and stale input.

Physical Watch verification and current product-image binding remain outstanding. The hardware acceptance sequence is open/edit/arm, Home/relaunch draft restoration, delivery while the UI is absent, dismiss/cancel, existing countdown/Points preservation, touch/Back, sleep/wake, memory and current draw.

Headless deployments select alarm control/scheduling without any GUI providers. Interactive terminal and remote web presenters remain future optional providers; neither is required or started by this prototype.
