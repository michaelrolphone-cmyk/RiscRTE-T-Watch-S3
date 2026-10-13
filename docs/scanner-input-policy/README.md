# Watch Scanner shared-keyboard lifecycle, later increment

Watch-only BLE Scanner 0.2.19 adds `PORTABLE_TEXT_INPUT_POLICY` to the exact selected 0.2.18 target command. The original feature flags, complete font set, imports, exports, grants, alias format, stop-before-naming behavior and checked persistence are retained. X4 Scanner 0.2.24 is excluded because its source attribution remains unresolved. Tonight's device artifacts remain sealed. The cumulative candidate keeps RF 0.3.4 and the other 52 ELFs unchanged. Calculator and Model Viewer receive only the explicitly selected metadata-gap layout packing; every section byte, program header, symbol and relocation remains identical, and neither application is rebuilt.

The frozen baseline is public Points receipt `33c62cb135174ef98286d34efb2c0d658a906ecd`, compiled recipe `b47f196b4199ebbdfe9ed74d0d4ef0ea277d8055`, store digest `f4c554a3df583ab0e3d56f37a491efb28d7fa197fbe5e5607704494dda7d8d92`. Its bound handoff SHA-256 is `245b77bada834635a69c65f5dd3517b76f3f1bf8cc71c8f723e4546aa95f4616`.

## Initial working checkpoint: capacity gate was open

The frozen baseline uses 19,410 object pages, exactly the two-block reserve floor. Scanner can grow from 146,972 bytes by 114 bytes without other changes, or by 365 bytes after the last eligible ordinary JSON page is recovered. Thus its current absolute fit ceiling is 147,337 bytes.

Initial policy-enabled target measurement is 151,068 bytes, +4,096. The already-tested Points nonallocated metadata-gap helper preserves all allocated bytes, addresses, alignment, imports, exports, relocation records and program headers while reducing that target to 149,392 bytes. This is still 2,055 bytes above the fit ceiling; the full candidate is held. No reserve, font, feature, authority or unrelated app has been removed. The recipe fails closed rather than materializing an over-capacity store.

The disabled flag rebuild is byte-identical to selected Scanner 0.2.18 (`07eb058652eaaf6ccd5da59e21bf3548354b2e6b61418e874afed367e3cd8b57`). Exact-source publication, final target/capacity qualification, final full-candidate normal/sanitized admission, source CI, recipe CI and independent review remain explicit gates. Preliminary tests and measurements are not hardware qualification.

## Recipes

- `scripts/build_scanner_policy.py`: exact inherited command, optional policy only, current source closure and font custody. `--provisional` permits only the current Utilities source to be modified. `--pack-metadata` selects the established metadata-only helper; `--flag-off` disables both the policy and that helper for predecessor equality.
- `scripts/test_scanner_policy_flagoff.py`: exact selected-predecessor equality and independent unchanged-application/current-dependency equality.
- `scripts/inspect_scanner_target_stack.py`: target disassembly entry-frame bounds and bounded static modal state/draft/client/checkpoint storage. This does not prove dynamic peak call-chain stack usage.
- `scripts/assemble_watch_scanner_policy.py`: frozen baseline custody, only the Scanner version increment and cohort source selection, lossless eligible JSON only when needed, two-block reserve, unchanged native image, all 55 ELFs admitted by real Runtime code in normal and ASan/UBSan host harnesses. No target instructions run.
- `tests/test_scanner_policy_recipe.py` and `tests/test_points_metadata_pack.py`: fail-closed source/custody, allowed delta, metadata semantic parity, capacity accounting and metadata packing tests.

No device flash or delivery is performed by these recipes. A final full-image digest is streamed only after the two-block reserve and complete-cohort checks pass; a full flash image is not materialized.

The held packed candidate passed 55-ELF normal and ASan/UBSan Runtime admission with byte-identical receipts and no hardware or storage callbacks. This is separate from packing: it still requires 19,419 object pages after eligible JSON compaction, nine pages over the reserve floor. See `provisional-measurement.json`.

## Approved packing-only companions

The cumulative recipe additionally repacks only `model_viewer.elf` and `calculator.elf` with the existing tested helper. Their exact original artifacts and original-source receipts are pinned in `selection.json` and `receipts/`. Model Viewer saves 1,752 bytes and seven object pages; Calculator saves 1,672 bytes and seven pages. These 14 pages cover Scanner's ten-page growth without compacting any additional JSON. The expected cumulative demand is 19,406 pages, leaving four object pages before the unchanged two-block floor, plus the unused eligible JSON page.

The initial capacity-blocked measurement is retained as historical evidence. It is superseded only by a final source-bound qualified receipt, not by the packing approval itself. Behavior replay exercises the original C sources under native host compilation; target admission separately validates the exact packed Xtensa ELFs. Neither is physical-device execution.

The selected Scanner source is now public Utilities `89e2132c4ed9b1e0372381f149be5c158ab1e666`. `qualify_scanner_policy.py` provides component-only packing/roundtrip and 55-ELF admission evidence without writing a candidate store, bank or full-device image. Final target, source/recipe CI, behavior replay and independent-review receipts are separate completion gates.
