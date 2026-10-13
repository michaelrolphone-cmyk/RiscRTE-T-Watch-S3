# Watch Scanner lifecycle: retained component checkpoint

This is a later, Watch-only component qualification checkpoint. It does not assemble, flash or deliver a device increment. Existing device artifacts remain unchanged. Qualification status and the complete source/artifact bindings are in `qualified-components.json`.

## Exact selections

- Scanner source: Utilities `89e2132c4ed9b1e0372381f149be5c158ab1e666`
- Compiled/qualified Watch recipe: `b022f6ea6628e346832996308821cae8d4cdd50c`
- Shared System: `9957e7c975f7b57ce9ea50d57b13c1d9bb75cf43`
- Watch SDK profile: `089868395268b696c05651c33816345bfe0425df`
- Target Runtime SDK: `267aab6d9382ce4921a1536fab1620749b2f5301`
- Admission Runtime: `64c8e52e46fd91e8fdafd636db04eed88f0c51a9`
- Cumulative baseline: public Points receipt `33c62cb135174ef98286d34efb2c0d658a906ecd`, compiled recipe `b47f196b4199ebbdfe9ed74d0d4ef0ea277d8055`, frozen handoff SHA-256 `245b77bada834635a69c65f5dd3517b76f3f1bf8cc71c8f723e4546aa95f4616`

Scanner 0.2.19 adds only the opt-in `PORTABLE_TEXT_INPUT_POLICY` flag to its selected target command. Original feature flags, fonts, imports, exports, grants, alias format, stop-before-naming and checked persistence remain. Disabling the flag reproduces selected Scanner 0.2.18 byte-for-byte: 146,972 bytes, SHA-256 `07eb058652eaaf6ccd5da59e21bf3548354b2e6b61418e874afed367e3cd8b57`. An unchanged-app rebuild with the current dependencies independently matches the same artifact.

## Bounded packing-only companions

Scanner alone exceeded the two-block reserve even after the proven metadata-gap packing. The approved solution repacks only the selected Calculator and Model Viewer artifacts with that same helper; neither companion is rebuilt or behaviorally changed.

| Artifact | Before bytes | Packed bytes | Packed SHA-256 | Object pages recovered |
| --- | ---: | ---: | --- | ---: |
| Scanner 0.2.19 | 151,068 | 149,392 | `ca704e18dca7eee1eb431e6c88f58998dfe0a482399ed7f82063073e553a5825` | Scanner's own metadata packing |
| Calculator | 115,864 | 114,192 | `e7394fea887144624c39c971c8f3771cebfed57d457403d2a3087748e8dc83bf` | 7 |
| Model Viewer 1.3.1 | 43,300 | 41,548 | `df54d45fb79182dc08913458dc5fa38214a92c8e3fc3eb222672f931fd7b58eb` | 7 |

Every section's content, every allocated section's address/alignment/file offset, all symbols and relocations, and every program-header byte are identical before and after each packing step. The one ELF-header exception is the four-byte `e_shoff` field at absolute offsets 32–35, which points to the relocated section table. The actual differences are at offsets 32 and 33. The first `PT_LOAD` includes that header field, so its bytes are identical except for `e_shoff`; other segment bytes are exact. Nonallocated section file offsets also move, as explicitly recorded.

The cumulative qualification contains 55 ELFs and 113 store files. Exactly five paths change: `ble_scanner.elf`, `ble_scanner.json`, `calculator.elf`, `model_viewer.elf`, and `cohort.json`. All other 52 ELFs, native firmware, boot authority and grants remain unchanged. RF stays at 0.3.4. X4 Scanner 0.2.24 remains excluded because its selected source attribution is unresolved.

The exact store needs 19,406 object pages and retains two free blocks, with four spare object pages before that reserve floor. No additional JSON is compacted; the last eligible JSON page remains recoverable. The SPIFFS packing/roundtrip is checked in memory, without writing a candidate store, bank or full-device image.

## Evidence and scope

- Scanner source: 38 normal plus 38 ASan/UBSan workflows; 618 matching frame files; legacy model/renderer gate passed
- Companion source behavior: Model Viewer 11 normal plus 11 ASan/UBSan Watch cases; Calculator seven plus seven; 84 matching emitted frames
- Recipe boundaries: 30 tests; metadata-gap packing: six tests
- Target evidence: exact flag-off and unchanged-app parity; bounded static modal storage; maximum measured modal entry frame 448 bytes
- All 55 exact target ELFs admitted by the real Runtime code in normal and ASan/UBSan host harnesses; byte-identical admission receipts and zero hardware/storage callbacks
- Scanner source CI runs `38350925703` and `38350925517` passed; compiled recipe CI `38351186017` passed
- Independent fresh policy replay: 15 normal plus 15 ASan/UBSan cases; the prior 76 Scanner workflows were separately inspected, not represented as another fresh rerun
- Independent review is source/artifact bound in `qualified-components.json` and `independent-review.json`

The Model Viewer behavior replay uses the selected receipt's exact SDK header bytes. Its `RiscFileOpenSourceV1.h` differs from the historical workflow Runtime pin by four contract-comment lines; preprocessed bytes are identical. The exception and the matching Git blob/commit are recorded. LeakSanitizer is disabled only for the verified container ptrace incompatibility; address and undefined-behavior sanitizers remain enabled.

Host behavior replays execute attributed C sources, not Xtensa instructions. Target admission validates the exact packed ELFs separately. Entry-frame inspection does not prove peak dynamic call-chain stack use. Physical-device behavior remains unverified. No subsequent Wi-Fi/UI increment is started by this checkpoint.

## Reproduction entry points

- `scripts/build_scanner_policy.py`: exact inherited target command and current source closure; `--pack-metadata` selects proven metadata packing; `--flag-off` omits both the policy flag and the new packing step for selected-predecessor equality
- `scripts/test_scanner_policy_flagoff.py`: both exact predecessor and unchanged-app/current-dependency equality
- `scripts/inspect_scanner_target_stack.py`: entry-frame bounds and static modal storage
- `scripts/qualify_scanner_policy.py`: component-only complete-cohort packing/roundtrip/admission, with no candidate store, bank or device image materialized
- `scripts/assemble_watch_scanner_policy.py`: separate later packaging recipe; not used to assemble a device increment for this checkpoint
- `receipts/`: exact original-source and selected-artifact identities for the two packing-only companions

The compiled recipe checkout remains at `b022f6ea...`; this receipt-only documentation commit does not change its selected component bytes.
