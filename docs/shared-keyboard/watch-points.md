# Watch Points shared input component

This recipe selects Points in Time 0.6.13 from the delivered Watch1.1.17
0.6.12 baseline. Custom-type names use the existing ui.text-input API1 host in
plaintext with the original 13-character capacity. DONE remains draft-only;
custom-type SAVE and point SAVE preserve their separate original semantics.
The only added Points boot authority is ui.text-input API1 instance0.

The builder requires the exact predecessor clients.json, delivered Points ELF,
frozen Watch feature profile and clean pinned source commits. It checks the
original component hash, all inherited feature flags, the Watch inputs,
unchanged scheduling/picker/writer sources, target dependency closure and
Xtensa loader structure. Its 155144-byte ceiling is the delivered component
size. Compiler -mno-target-align removes optional Xtensa branch-target padding;
no application feature, loader relocation or reserve is removed.

The selected current adapter has checked terminal custody and cooperative
capture. PORTABLE_WATCH_COLOR_ONLY rejects incompatible displays and excludes
only the unreachable portrait Paper Quick Controls for the 240x240 RGB565
product. PORTABLE_WATCH_FROZEN_ICONS selects byte-identical delivered Watch icon
assets with provenance. These are explicit product selectors; unselected
System consumers retain their generic behavior. The frozen app already had a
no-Paper override; that selection is now local to its Watch branch because the
current adapter owns a strong generic Paper entrypoint.

Use test_watch_keyboard_points.py on the generated build receipt. It compiles
production Points, adapter, compact scene host and text host against the exact
target feature macros (omitting target-only optimization flags for host C).
Cases run normally and with ASan/UBSan and exercise nested navigation,
schedule edits/save/cancel/delete, name/color saves, separate draft acceptance,
Back/Home, repeated reopen, capacity/empty/delete, delayed presentation,
four repeated-key edges within12ms with no intervening frame, unavailable or
retained cleanup and runtime loss at modal/storage boundaries. Transport,
clock and local crown/sleep boundaries are deterministic host fixtures.

Final integration replaces only points_in_time.elf/json and appends the one
text-input grant to its existing policy row. Preserve all Files/Viewer,
Scanner, RTC, SD and other independent component changes. Regenerate the
combined product identity, perform ordered SPIFFS packing and full normal and
sanitized Runtime admission. At least two free blocks must remain; never
relax the reserve, resize a partition or delete an app to admit the component.
These are host/source qualifications, not executed Xtensa/hardware proof.
