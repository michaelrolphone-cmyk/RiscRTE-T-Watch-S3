# Lists shared text input

Build the selected Lists client and the shared text checkpoint and opt-in scene continuity hosts over the pinned qualified Contexts union. The same scene application has no device-specific compile defines or embedded fonts. Selected shared builds freeze the historical RiscSceneResidentV1.h from System eec748ca, with byte custody recorded in Productivity sdk/lists-selected-profile/source.json. Watch retains namespace 62 and its compacted loader metadata profile; X4 retains namespace 63, foreground lifecycle, and all old SD files. The sole new grant is ui.text-input@1 instance 0. The selected version becomes 0.1.2.

The presentation profile, all compiled font bytes and layouts are preserved. Scene host advances from Watch 0.4.5 / X4 0.4.4 to 0.4.6 with runtime opt-in continuity; no extra compile flags are added. The text host advances from Watch 0.1.6 / X4 0.1.5 to 0.1.7, retaining its exact ui.scene-only authority. Native firmware and all other providers are unchanged. Do not compile paused or unpublished SD-settings sources. Generated evidence is local, held until 2026-10-12 23:30 UTC, and is not a hardware qualification.

## Local recipe

Invoke build_lists_shared_input.py with --productivity, --productivity-commit, --system, --system-commit, --runtime, --watch-tools, --baseline (the selected Contexts candidate directory), and --output. Sources must be clean, exact-pinned and descend from Productivity 395c48de8fa10b672816c89c02dd9a5d4987a094. The sole added application define is PORTABLE_LISTS_SHARED_TEXT_INPUT. build_lists_text_host.py takes --system, --system-commit, --runtime, --watch-tools, --baseline and --output; it compiles only Services/text_input/host.c with no defines and independently repeats the raw target build. The app builder is run twice for reproducibility. The device wrapper inventories actual compiler dependencies and checks canonical staged headers against the build receipt.

Use assemble_watch_lists_shared_input.py with --baseline-components (the Contexts component root), --native-candidate (the unchanged Files native candidate), --lists-build, --text-build, --scene-build, --runtime, --system, --system-commit, and --output. Run once with SANITIZE=0 and again with SANITIZE=1 and --verify-only. Its two complete 55-ELF receipts must match. The exact store delta is lists.elf, lists.json, text-input/driver.elf, text-input/manifest.json, ui-scene/driver.elf, ui-scene/manifest.json, boot.json, and cohort.json; all other bytes are preserved.

Run inspect_lists_target_stack.py against the built app target and inspect_lists_text_target.py / inspect_lists_scene_target.py against the built hosts and test_lists_flagoff_target.py against clean predecessor/current Productivity checkouts. The latter requires byte-identical flag-off raw and compacted ELFs and manifest equivalence between preceding and new application source on the current SDK pins. Historical selected raw and compacted identities are independently reproduced with Runtime SDK a9587bec and System SDK eec748ca in selected-sdk-provenance.json; the generic current SDK updates an inline helper, so generic current-pin raw bytes differ from those historical images. A third flag-off case stages the selected frozen helper plus text contracts but omits the opt-in macro; it must reproduce both selected historical ELF hashes exactly. Target static frames do not prove dynamic peak stack or physical behavior.

## Historical text-host custody

`test_lists_text_predecessor.py` reproduces Watch compacted text host 3b71583 from published System 7fb13b09 (0.1.6), and X4 raw text host 5517367 from published System e3fd26c (0.1.5), using the selected current Runtime pins. System 7fb13b09 added the optional long-text ABI suffix and a wider internal draft state; it is not byte-identical to the selected X4 0.1.5 host. The new 0.1.7 host must therefore pass legacy base/extended-client regressions as well as checkpoint tests. No historical source or selected provider byte is overwritten.

## Exact scene profile and fonts

`build_lists_scene_host.py` accepts the same source/runtime/baseline arguments as the text-only builder. It compiles only the selected scene host: Watch retains `-DSCENE_HOST_TELEMETRY=0 -DSCENE_HOST_WATCH_240=1`; X4 retains no feature defines. Runtime flags `RISC_SCENE_FEATURE_POLICY_INPUT_CONTINUITY` and `RISC_SCENE_RESUME_FOCUS_CHANGED` opt in without changing old clients. All manifests preserve existing dependencies and capability grants.

The tracked font tree is pinned to 28a2ae80bef4537aacd626a507900c19b071bad1. X4 also requires the ignored generated telemetry font: the recipe runs the unchanged generator in its own output directory using Pillow 12.3.0 and requires exact SHA256 2d7501e42d6223ebbc191817715431182c435fea944a1a02166a0748a577eaf1. It never rewrites the System checkout. Every compiler-used font is hashed and compared with the selected inputs. `test_lists_scene_predecessor.py` must reproduce exact selected Watch and X4 host ELFs before final qualification.

## Watch resident role

The exact selected boot has no resident_shell configuration. Its default Clock 0.11.5 has no PORTABLE_RESIDENT_POLICY define or resident owner source in the 98-file selected closure. Clock SHA256 90388f2269badefae66d8ba7fc844fd7d7af481392e55bb79f9e898e4ff81875 remains untouched. Lists uses its existing non-resident path on this device; no owner or Runtime firmware replacement is composed.

## Final published source selection

`source-selection.json` selects published System `f4b30f8ebcc6d8cb905c8e90c91b1691acbe8165` and Productivity `f83d79a0753c2a451730000d2f553aa21fda7830`, with the unchanged per-device Runtime pins. Pass these exact commits to the builders. This file records source selection, not a completed final published-recipe qualification. Final candidate receipts must be generated from the exact API-published device recipe commit and kept distinct from any later receipt-only commit.
