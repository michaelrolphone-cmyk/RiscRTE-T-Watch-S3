# Current Watch app cohort

The explicit app-data profile combines File Browser 1.4.0, BLE Scanner 0.1.0,
LoRa Messages 0.1.1, Spectrum/Spectrogram 0.4.0 and Timecard 0.1.0 with the
existing Clock, Points, alarms, settings, update and audio tools. It contains
19 executable apps, 17 visible launcher entries and 17 selected provider
instances. Existing sleep, Quick Controls and radio cancellation hooks remain
part of every app's Watch profile.

Spectrum and Timecard use distinct native app-data namespaces 2 and 1. Spectrum
keeps KV API2 namespace7; shared preferences remain KV API1 namespace1, and the
LoRa picker keeps its versioned profile in namespace9. File Browser receives only
the read-only installed-files allowlist. Watch navigation is explicitly supplied
through its local battery-event adapter.

The complete development store contains 72 files and 3,845,523 payload bytes.
It requires the opt-in ABI2 layout with 0x510000-byte SPIFFS banks, 0x260000-byte
native slots and an independent 512 KiB app-data partition. The initial full BIN
overwrites saved settings and application data; no data-preserving migration is
implemented. Ordinary OTA must exclude the empty initial app-data image.

The preceding 18-app/Spectrum0.3 cohort used 70 files and fit the unchanged ABI1
layout. Its preserved artifacts remain separate. New source pins cannot silently
turn those historical images into app-data deployments. Full original app ELFs
remain debug artifacts; only verified loader-equivalent application compaction
is installed, while provider ELF bytes are unchanged.

See [current-apps-overlay.md](current-apps-overlay.md) for exact geometry,
authority, build commands, loader memory measurements, overwrite classification
and validation limits. The configured source pins, build records, actual final
store hashes and exact-head CI determine candidate provenance. Source preparation
and host execution do not qualify physical wake, RF, heap or flash behavior.
