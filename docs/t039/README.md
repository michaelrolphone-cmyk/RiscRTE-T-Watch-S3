# T039 BLE Buttons / T037 shared HID

Cumulative composition from the exact T046 delivered image. Buttons 0.1.26
preserves each validated queued tap and sends one press/neutral pair per poll.
Cancellation, subscription/security changes and connection generations clear
pending commands. Four configurable assignments, shortcuts, held keys, mouse,
pairing, reconnect and Forget remain. This repairs a reproduced queue loss;
physical device/radio/OS interoperability remains untested.

Wave additionally moves shared HID 0.1.2 to qualified 0.1.4. Watch and X4 already
carry the exact same 0.1.4 bytes. Native firmware, boot registration, grants,
other apps and prior fixes are preserved. X4 requires its cumulative SD overlay
with the BIN. The overlay adds Apps/ble_buttons/ble_buttons.elf and its manifest, updating the
existing installation; all files from the .116 overlay remain byte-identical.

## Reproduction

Use source-pins.json and evidence/buttons-build.json for immutable dependencies,
actual compiler command and the complete compiler-reported source closure.
Build scripts/t039/build_buttons.py with --utilities and --system checkouts,
--output a fresh package directory, and --watch-tools the T-Watch checkout.
Compiler defaults to PlatformIO Espressif 8.4.0; --compiler overrides its path.
Color: --profile scripts/t039/profile/color-command.json --color --bridges
/pinned/RiscRTE-Watch --runtime-sdk /pinned/Runtime. Generated catalog and alarm
compatibility header are preserved under profile, including the exact header
from the pinned historical Utilities source. X4: --profile
minimal/t039/profile/target-x4/ble_buttons/x4-native-app.json (no --color).
Its frozen delivered SDK header profile is overlaid with pinned System headers.
Both target profiles reproduce the final compact ELF byte-for-byte. Original
absolute commands remain audit data; the script maps them to explicit inputs.

Run scripts/t039/assemble.py with --baseline the exact T046 BIN, --buttons
built package directory, --hid the qualified 0.1.4 package, --runtime native
profile Runtime checkout, --watch-tools Watch checkout, --product-repo this
checkout, --product watch/wave/x4 and --output a fresh directory. X4 additionally
requires --previous-sd pointing to the exact .116 cumulative SD archive.
Assembly verifies the full baseline hash, complete-store roundtrip, limited
file delta, repeated identical SPIFFS packing and unchanged non-store/non-bank
flash bytes. It never compiles native firmware.

Qualification is in Utilities docs/t039 (32 FT6336U cases, X4 app/adapter/GT911
slow asynchronous display, Wave native geometry, configuration/persistence/mouse,
and secure NimBLE ATT ordering), and Drivers docs/t037 (full protocol suite).
Full-image admission is recorded here after assembly. No hardware was flashed.

## Installation

Test builds only. Full 16 MiB factory BINs flash at 0x0 and erase internal user
data; back up before flashing. For X4, overlay the cumulative SD ZIP onto the
existing card, preserving every other file and settings directory.
