# System quick controls candidate

The supplied interactive reference is preserved in `quick-actions/original.html`.
This increment uses the same shared NOVA-7 controller/renderer in Clock and every
foreground app in the current profile. The original top-edge gesture, full-width
panel, segmented controls, fonts and tile arrangement are retained, with Font
Awesome equivalents.

Current candidate: saved brightness, notification volume (default 50%), Silent,
Torch, shared Wi-Fi enable policy, real Bluetooth controller control and Airplane
restoration. DND silences sound and vibration for Alarms, Countdowns and Points
in Time, retaining visual alerts and occurrence bookkeeping. Muted occurrences
remain muted after DND is disabled or the provider restarts. Points uses the
same selected notification-volume scaling; its pulse/cadence is unchanged.

Brightness is restored after Light/Deep wake, refused sleep, notification
preemption and Torch exit. The one-minute idle timeout, selected Clock face,
app navigation and notifications remain in their original owning paths.
Frequency Generator's own level is unchanged. No alternate keyboard is introduced.

Build current app cohort using `scripts/build_current_apps.py` and the exact
`apps/current-apps-sources.json` pins. `apps/current-runtime-requirements.json`
selects the explicit grant/provider-key capacity and bounded HCI Runtime. Frozen Watch 1.0.1 release metadata and
historical Points/audio/update custody lanes are retained unchanged.

Verification: shared real-adapter tests and native renders in System-Apps;
`test_quick_clock.py --system-apps PATH`; existing Clock/launcher/sleep suites;
current-store target ELF validation and exact-image host Runtime re-execution.
The latest-main CI lane builds the reviewable 16 MiB flash image; no flash,
merge or release is performed. Native renders are genuine C renderer output.
The interactive HTML reference could not be rendered in the local cloud shell
because Chromium sockets are restricted; no browser comparison is claimed.

Double-tap wake and five-minute Hybrid wake recovery are separate future work.

The owner requested the local DND-all BIN before broad verification/hosted CI.
Its exact local source trees are preserved as remote commits in the source
provenance record. The16MiB image at offset0x0 replaces both banks and saved
NVS state; it is a user hardware-test artifact, not a released/qualified build.
