# Shared 26-app factory suite qualification

Built source revisions remain the pins in `final-verification.json`; this later documentation commit does not change either firmware or application ELF. The same 26 application ELFs are present on both watches. Waveshare LoRa is provisioned at `Apps/lora_messages/lora_messages.elf` on external media; Home stays internal.

Both full factory images target 0x0 and ERASE saved settings, NVS and AppData. They are not OTA migrations. No hardware was accessed or flashed. Native and host checks do not qualify hardware.

Normal and ASan/UBSan admission passed for 59 internal T-Watch ELFs and 60 internal Waveshare ELFs with zero hardware/storage calls. The external LoRa ELF passed both native public-export validators. T-Watch preserving-cohort admission passes. Waveshare preserving admission rejects the new LoRa consumer of existing namespaces without explicit migration; the guard is unchanged.

ABI3 layout, initialized 512 KiB AppData, original provider binaries/policy and panel_vendor are unchanged. Declaration/grant capacity is 32; live handles remain 16. Home missing-media feedback and lossless atlas encoding are tested; optional media/radio UI evidence is recorded in qualification.json.

Reports under this directory are immutable build-time evidence. Historical publication/Library status in them predates the approved source publication and is not a current service-status claim. Recovery archives remain preserved locally; `held-artifacts.json` records their hashes. Uploads are blocked by the helper endpoint not exposing Library tools. Build delivery remains held until 2026-10-13 23:30 UTC.

Reproduction scripts preserve the exact local execution paths as evidence. Resolve their source/checkpoint paths before running in a different environment; no script here accesses hardware or publishes source.
