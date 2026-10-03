# Clock, shared Springboard and Battery software milestone

This optional deployment preserves clock-first startup and is separate from the
clock-only PR4 baseline. Tap and release the clock to open the shared Springboard.
Tap Clock to return, or Battery to inspect voltage/charge and refresh with Update.
Upper-left Back returns a child to the default clock. In Battery, bottom
Previous/Next controls scroll rows. Every new app requires neutral touch first,
so a held finger cannot accidentally launch the next app.

Springboard source remains in RiscRTE-System-Apps; Battery source remains in
RiscRTE-Utilities. A shared client-side adapter links their existing app logic to
canonical display.output@1, input.touch.raw@1 and board.battery@1 grants. No new
runtime SDK, hardware UI in firmware, duplicate Watch Battery/Wi-Fi app, catalog
service, sleep implementation or settings framework is introduced. The bounded
compiled catalog explicitly lists only Clock and Battery. No storage grant is
available, so Home editing is disabled.

Build the shared source revisions recorded in `shared-app-build.json`:

```sh
python scripts/build_twatch_drivers.py
python scripts/build_launcher_apps.py --system-apps /path/to/RiscRTE-System-Apps --utilities /path/to/RiscRTE-Utilities
python scripts/build_clock_deployment.py --profile all --launcher
python scripts/verify_clock_deployment.py dist/launcher-deployments/*.zip
```

Each explicitly selected profile adds the existing secondary I2C and FT6336 touch
modules to the five-driver clock closure. GPIO1, I2C2/3, PMU4, panel5, touch6 and
RTC8 are separate ELFs. Bus102 is added; PMU setup still enables only declared
display/backlight rails1/2. Per-app boot grants bind the exact display/touch/RTC/
battery instances. The app cannot gain a capability merely by being in the menu.

Use the clock installation prerequisites, matched firmware/partition/store
artifacts, checksums and full early serial diagnostics from `CLOCK_INSTALL.md`.
This bundle must replace an empty store; do not merge with stale payloads. The
clock-only archive is still independently buildable. The launcher bundle carries
its own version, source SHAs and hashes; it is not the older clock artifact.

Host app/service fixtures and real Xtensa builds are separate from the actual
runtime bus-model integration and from physical verification. The physical Watch
is unavailable; no profile is inferred and no flashing occurs. Physical touch
coordinates, display colors, PMU readings and startup remain to be tested.
