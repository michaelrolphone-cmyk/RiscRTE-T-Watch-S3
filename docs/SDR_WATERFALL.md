# SDR Waterfall test increment after Watch 1.0.2

This source prepares Watch 1.0.4 with Waterfall 0.1.2, experimental
`s3-radio-iq-v1`0.1.1 and the opt-in Runtime 0.1.34 IQ resource. It does not
publish, merge, install, flash or qualify hardware. Released 1.0.2 and its frozen
inputs remain immutable. All19 existing applications and data namespaces remain;
the candidate has 20 app policies, 18 provider instances and 18 launcher entries.

The app uses only `radio.iq@1` plus its normal shared app services. The driver
requires `platform.radio.iq.resource@1`, a CPU-owned capability present only in
`esp32s3-16mb-appdata-iq`. It cannot claim or touch the modem at boot. Each
capture uses an exclusive, owner-task resource lease and restores/parks before
release. Wi-Fi/BLE/native mutation and sleep/exit are excluded while leased.
Failures retain custody and retry; normal app display/storage I/O waits for
positive cleanup. Airplane mode prevents capture. START/PAUSE retries reception;
sleep pauses it. LO is fixed 2440 MHz, receive bursts are 256 signed 10-bit pairs,
and the existing FFT supplies four-tone rows. Every successful row repaints.

The native target reserves the entire64 KiB dump bank 0 at 0x3FCB0000 before heap
initialization. Final ELF proof checks DRAM/IRAM aliases, heap/static bounds,
exact reservation and pinned ROM entries. This reduces available internal heap
by64 KiB even while SDR is idle. Loader code/data remain in PSRAM. Hardware free
heap and physical radio/audio coexistence are still measurement tasks.

## Data-preserving staged installation

A direct1.0.2→SDR cohort is rejected by the released validator: it cannot bind the
new resource or grant a new app an existing namespace. There is no new full-wipe
migration. The original board stays byte-identical; no ownership is inferred
from an installed app name or a changed hardware record.

1. Prepare/publish release 1.0.3 with only the native-stage catalog and exact Runtime 0.1.34 image.
   Built-in Firmware Update clones the existing boot store, changes the inactive
   native slot, verifies both and restarts. Confirm Clock health before proceeding.
   The app store/cohort identity remains1.0.2 and all saved data remain in place.
2. Prepare/publish release 1.0.4 with the cohort-stage catalog. Built-in Firmware Update installs
   exact native+bootfs in the inactive pair, then restarts and confirms Clock.
   The explicit boot `cohort_migration` record binds source 1.0.2/27876749 to
   target 1.0.4 and lists only new app Waterfall, KV API 1 namespace 1. Runtime admits
   this only because every existing app already shares that exact preference
   grant. Private KV, app-data, provider bindings and existing owners remain
   protected; wrong origin, extra grants, API changes and reassignments reject.

Both normal payloads exclude NVS, app-data, bootloader, partition table and
initial empty data images. Each transaction retains the preceding complete pair
for rollback. A separately labeled full 16 MiB image is initial provisioning only;
it erases data and must never be substituted for either upgrade stage. Current
clients require immutable published assets and the reviewed catalog stage;
a local ZIP or CI artifact is not directly installable through them.

## Verification and artifacts

- `scripts/build_current_apps.py --drivers <exact driver checkout> ...` builds
  the complete current app cohort from pinned, clean sources.
- `scripts/build_sdr_cohort.py` verifies released 1.0.2 bytes, unchanged hardware
  and old grants, native reservation proof, full source/component hashes, store
  bounds/round-trip and both installed-provider catalog grammars. It prepares
  two catalog snapshots, native-only and paired-cohort inputs, initial-only image,
  notices and explicit instructions, without changing the live catalog.
- `scripts/test_sdr_upgrade.py` exercises released 1.0.2's actual native adapter
  and the new adapter with real candidate image bytes, preserves non-empty NVS/
  app-data sentinels, and checks cancellation, corruption, interruption points,
  retained selection, previous-pair rollback and exact staged graph/ELF admission.
  The previous native→store mapping is never relabeled or rewritten as a source.
- Current loader proofs validate all 37 ELFs, 20 app policies and 18 provider
  instances. Current Clock startup executes the production IQ driver too, with
  every MMIO/ROM hook set to abort: no boot-time capture is permitted.

Tests replace physical flash/SPIFFS/TLS and do not execute Xtensa instructions
on the host. Physical RF/PLL/sensitivity, power draw, wake, target heap headroom
and OTA power-loss qualification are unrun. Vendor PHY calibration is not linked;
software success does not establish useful RF reception.

The two stages have distinct immutable release rows, 1.0.3 then 1.0.4.
The prepared final index is computed from the native-stage index, so same-version
collisions cannot be hidden by deriving both from the old index. The native
bridge keeps the existing 1.0.2 cohort anchor, including in its initial-only image.
