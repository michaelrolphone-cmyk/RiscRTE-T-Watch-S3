# Watch 1.1.17: shared Wi-Fi keyboard test increment

This increment makes the Watch Wi-Fi SSID/password editor a real client of the
shared `ui.text-input@1` capability. Wi-Fi 1.1.28 requests masked password entry;
the shared text service owns the draft, Show/Hide state, cancellation and cleanup.
The source-level keyboard capture fixes apply to repeated characters and queued
touch contacts. The initial state is masked and reopening starts masked again.

This is not a claim that every Watch editor has migrated. BLE sensor naming,
Points/custom text, Files, LoRa and the other legacy editors remain unchanged.
The universal shared-keyboard migration remains open. No hardware keyboard or
USB host is added to Watch; its selected shared provider uses its existing touch
interface. X4 can independently select the same service's USB composition.

## Frozen predecessor and narrow changes

The predecessor is Watch 1.1.16 product
`628f72b09786880edeafa7c161aedd7114c2d7bc`, full-image SHA-256
`63a89adf489ff568bb4236c0f4378f5b707554ec1f9394bd45ed58c71e52a7ef`.
Its later published test-only lifecycle custody successor is included in this
source branch without changing any frozen image input.

`scripts/assemble_watch_shared_keyboard.py` permits only:

- Wi-Fi ELF and manifest, advancing 1.1.20 to 1.1.28 and adding one text capability
- Scene ELF and manifest, advancing 0.3.2 to the explicit Watch-compact 0.4.3 profile
- The new text-input-host 0.1.4 ELF and manifest
- Boot registry: one additional provider and one Wi-Fi text-input grant
- Cohort identity and its associated initial-bank digests

All 105 other existing store files remain byte-identical, including mounted Files
1.5.31, Clock 0.11.5, every other app, the existing compact-color scene profile,
all hardware drivers, their grants, and settings/storage policy. There are still
25 apps, now 31 registered provider instances and 55 admitted ELF files.

The complete native firmware remains Runtime
`267aab6d9382ce4921a1536fab1620749b2f5301`, ELF SHA-256
`7025c5158323a0b26a62c3608684a3eecdbfd74e42049ba760f57822315307f0`,
firmware SHA-256
`f9cc819421775cfb9e55a8c7b2c1f2174c9a61b1a85560446cf4f680d14a7726`.
No native build, partition change or SD persistence work is included.

## Watch size profile and API boundary

The universal scene 0.4.2 contains optional OBD telemetry that was never installed
on this Watch. Its compact ELF is 297,836 bytes, versus 197,584 in the predecessor;
that pair does not fit the frozen bootfs. LTO alone makes it larger (305,668 bytes).

The explicit `watch-compact` source profile omits only the optional telemetry
implementation and fonts, with no telemetry API advertised. It retains legacy
scene, components, page, checkpoint, reading, reading-links and shared keyboard
behavior. The separately versioned scene-host 0.4.3 also selects the existing 240×240 RGB565
geometry explicitly and omits unreachable 2× component font data. Other formats
or dimensions fail closed. The final compact ELF is 159,128 bytes; 240px
component, reading and keyboard pixels match the unrestricted reference.
The ordinary default/X4 build remains unchanged. It is not valid to label the
Watch profile as the generic 0.4.2 artifact or to copy its excluded telemetry API.

Watch retains its four selected scene dependencies: display, raw touch, clock and
compact-color presentation. The generic navigation dependency is not introduced.
The text provider requires only the scene capability. All existing source-bound
application grants remain intact.

## Reproduction and qualification

The common final System source is
`9c0ad2faa4b3aa73daf1c92cc343e0f83c2a5af3`, tree
`d63b624b1dd397afd38cdb4db0b4cf94c53ba409`. Both the scene and Wi-Fi
components use that one source identity.

Build Wi-Fi with `scripts/build_watch_keyboard_wifi.py`, supplying its explicitly
pinned source repositories, frozen Watch profile, predecessor app receipt and
frozen store. The exact prior Wi-Fi SHA and feature flags must match. The complete
Contexts catalog, alarm Watch suffix ABI, display/touch orientation, cooperative
RGB565 rendering through the current raster-snapshot successor, quick toolbar, BLE/Contexts and sleep features are retained. The shared
client and its required checked-storage, native-custody and terminal-retention
safety guards are enabled. No SD checkpoint policy is enabled. Local Watch PMU Back continues to be polled
while text is active; an entry-held press is ignored until neutral, a fresh press
cancels, and failed or retained callbacks fence subsequent provider calls.
Touchscreen Home closes the app without queuing nested Back, so the unchanged
Runtime returns it to the default Clock.

Build the published System text-service recipe using `--host-profile watch-compact`.
The pair builder records every source and SDK header hash. The product composition
rehashes all those inputs and the Wi-Fi compiler dependencies, checks ELF byte
identities, applies only the approved loader-metadata compaction and preserves
all retained ELF code/data/symbol/relocation semantics.

Run the product recipe with the frozen full image, unchanged native pair, exact
Runtime and System checkouts, recorded SDK checkout, keyboard pair and Wi-Fi
output. Run again with `--verify-only`, then with `SANITIZE=1` and
`ASAN_OPTIONS=detect_leaks=0`. The final-image admission receipts identify the
precise product/source trees and full-image hash. Hosted workflow and keyboard
checks are complementary to admission; admission does not execute target code.

The measured boot-order packing algorithm and every existing file's relative
access order remain unchanged; only the new provider's two paths are inserted.
The minimum two-free-block reserve is mandatory. The recipe refuses a full store,
changed source input, unused-provider-only composition, extra grant, changed
unrelated file, mismatched bank digest or mismatched source-qualified native pair.

## Delivery limits

The plain 16 MiB BIN is an initial full flash at offset `0x0`. It erases internal
settings, saved Wi-Fi and app data. Watch uses internal flash and has no SD
installation package. Do not call this an OTA or data-preserving update.

Preserve exact symbols, build receipts, full-image admission and source custody
alongside the image. These are software checks; no physical Watch touch, radio,
boot, sleep, pairing or performance qualification is claimed for this image.
