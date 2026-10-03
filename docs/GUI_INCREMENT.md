# Watch GUI increment 0.4.4

Built from the physically confirmed 0.4.0 and touch-direction control. The original PMU/panel, every physical driver ELF and manifest, board wiring, and paired runtime remain byte-identical. No new provider is installed.

The application changes cover completed-first-frame startup brightness gating, simultaneous outgoing blur/fade and incoming blur-to-sharp transitions, Clock-to-Springboard held gesture continuity, sampling input while full frames drain, bounded motion and layered tap selection, and crown Back outside Clock using the original PMU short-event API through an app-local navigation adapter. Crown in Clock and its current light sleep behavior remain. Deeper sleep modes are separate later work.

The store has exactly 22 files. The 13 board/physical-provider files must match the actual original CI artifact hashes in GUI_BASELINE.json; only four application ELFs, four application manifests, and boot grant policy may change. All display presentations remain full 240-row frames. The earlier failed 0.4.1–0.4.3 display/provider changes are excluded.

Host models, sanitizers, target compiler/ELF checks, CI, SPIFFS round trips, and binary provenance are software evidence. Hardware verification remains necessary. Startup gating covers the application-visible interval; a possible earlier rail/GPIO interval is not claimed resolved without observation.

BIN address 0x0 overwrites the lower 8 MiB, including NVS/settings. The upper 8 MiB remains untouched. Preserve both confirmed older images. No flashing, merging, or release publication is performed.
