# Watch LoRa shared input integration

LoRa Messages 0.1.14 routes message and RF-value entry through the separate
`ui.text-input` host. It retains 240-byte printable-ASCII messages and 11-byte
RF drafts. Done updates only the draft/validated value; explicit Send retains
its original raw broadcast, no receipt, no automatic retry behavior.

The recipe verifies the exact 0.1.13 predecessor payload and compile selectors,
uses the previously published Watch color/frozen-icon profile, and selects an
exact font subset containing every face the LoRa/Quick Controls/alarm path uses.
All original glyph bytes and metrics for those faces are preserved. Generic
consumers are unchanged. `radio.lora` authority and all prior grants remain;
only `ui.text-input@1` is appended to this application's policy.

`build_watch_keyboard_lora.py` produces the target component, preserving the
full inherited Contexts catalog and all sleep, radio, alarm, and NOVA flags.
`assemble_watch_lora_shared_input.py` composes only LoRa, scene/text hosts,
boot policy and cohort identity over the complete Files/Viewer/Scanner/RTC/
Points candidate. It verifies all 113 store files, 55 target ELFs, the existing
native firmware and minimum two free SPIFFS blocks. It writes a compact overlay,
not an independently delivered firmware image.

The current X4 candidate contains no LoRa app or LoRa radio provider; no X4
application or target payload is changed by this component.

No hardware testing or flashing is implied. Delivery remains held until
2026-10-12 23:30 UTC. A later complete union must preserve any newer independent
work and repeat full-cohort admission before delivery.

## Qualified checkpoint

The exact compiled Watch recipe is `a0ad6032d7969816d63e6593e6863bc23e18d6d8`.
Its complete cohort passes normal and ASan/UBSan admission with 55 ELFs,
113 files and three free blocks. LoRa is 124,724 bytes. All 58 application
workflow runs pass; the bounded font selectors preserve all 25 comparison
screenshots, including 17 non-editor views.

`integration-receipt.json` binds the independent published System/Utilities
sources, local integration patch mapping, original deployed feature flags,
component hashes, validation limits and preserved newer work.
`qualified-components.tar.xz` contains the eight-file overlay and compact
proofs; `archive-manifest.json` lists every member hash. It contains no native
firmware or full-initial image. The archive was decompressed and verified.
Extract only for integration; do not copy its complete boot/cohort policy over
a newer union. Repeat full admission after combining independently newer work.

Utilities CI passed. System and Watch working branches do not trigger their
branch-filtered workflows, so no remote CI pass is claimed for those repos.
