# Audio Tools integration: incomplete checkpoint

**Not ready for integration, hardware testing or BIN delivery.** Read
[AUDIO_CHECKPOINT.md](AUDIO_CHECKPOINT.md) before resuming. Source was recovered
after an execution-workspace replacement; no pre-replacement test artifacts or
logs survive. The descriptions below specify implemented gates and intended
coverage, not a claim that this reconstructed revision passed them.

## Additive scope

The generator uses the existing deployed `twatch-speaker` and board-selected
I2S1. It opts into shared `PORTABLE_AUDIO_SESSION` and `PORTABLE_ALARM_CLIENT`,
with existing rotation0, local PMU crown Back, touch and Hybrid sleep. No new
audio stack, firmware UI, OTA or App Store implementation is introduced.

All 44 baseline Wi-Fi store paths must remain. Only Springboard ELF/manifest
and additive boot policy may change. Existing app/provider/service bytes, board,
Clock/Points namespace1+5 grants, 32 faces, original seven service keys and saved
Wi-Fi format are preserved. Springboard uses its original adapter with a new
catalog/version; only the audio app uses the new audio adapter.

Each deterministic overlay embeds its verified original archive. Verification
uses the existing Wi-Fi custody verifier and independently checks normalized
baseline store bytes against the fixed delivered44-file baseline. Exactly eight
profiles plus common are required. Their complete stores must match after only
the historical board.revision normalization; common board bytes stay unchanged.

## Build and custody gates

- `build_audio_apps.py`: exact clean shared-source pins, configured target app and
  catalog-only Springboard, import/export/ABI checks, second clean target rebuild.
- `build_audio_deployment.py`: eight additive profiles and common, exact source
  provenance, unchanged old app policies, no existing app loss.
- `build_audio_store.py`: reuses the pinned existing SPIFFS packer and independent
  unpack/byte comparison; no alternative filesystem/image implementation.
- `test_audio_deployment.py`: real-artifact negative checks, including a valid
  target ELF with refreshed self-reported checksums rejected by source rebuild.
- `check_runtime_store_admission.py`: real Runtime admission of every complete
  production store, including image extraction, with no native I/O.
- `test_production_store_runtime.py --audio`: replaces executable architecture
  only, retaining all production board/boot/manifests/policies unchanged.
- `build_audio_flash_bundle.py`: exact successful six-job CI receipt, clean Watch
  commit/tree, pinned Runtime artifact, fresh target-byte source rebuild, all
  archive/image/final-BIN admission and actual final-store ASan/UBSan execution
  before writing a BIN. A required Runtime component descriptor is still absent.

The production-source harness uses actual Clock, audio app, Springboard, return
Clock, alarm service, FT6336, PMU, panel and speaker providers through Runtime.
Only raw hardware callbacks and in-memory KV are modeled. Planned cases include
Start/Stop/restart, touch/crown Back, healthy bound storage while playing, open/
write/partial-write/close failure, retained cleanup with no late I/O/storage or
unload, display failure, failed touch with crown escape, Hybrid Light sleep/wake
without automatic audio restart, and real alarm preemption/durable dismissal.
An additional persistent-health-failure/default-Clock case remains unresolved.

The added sixth `audio-integration` CI job depends on the original Wi-Fi job.
All existing five jobs remain required, including actual default Clock and the
namespace1+5 admission regression. No merge or release has been performed.

## Hardware boundary

Host tests do not execute Xtensa instructions, play sound, record a microphone,
use RF or write a device. Physical sound levels, wake/current, dynamic heap and
durability remain unqualified. Whole-image installation at0x0 would replace the
lower8MiB including erased NVS, resetting Settings, Stopwatch, alarms/countdown,
Points and Wi-Fi profile. Upper8MiB remains untouched. Keep the accepted Watch1.0
image for recovery. No installation is authorized by this incomplete checkpoint.
