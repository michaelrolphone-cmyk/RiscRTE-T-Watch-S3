# Watch normal-browser source Open

The optional overlay adds Files 1.5.33 and Model Viewer 1.3.1 to the exact
complete 1.1.17 baseline. The only new grants are `file.open.source@1` for
those two applications. Every existing app, provider, handler declaration,
export map and grant remains intact, including shared keyboard, RF, alarms,
RTC, wake, Contexts and local/remote browser controls.

`bind_watch_file_source.py` checks the component receipts and exact authority
baseline, then writes five changed store members and the native build profile.
It does not create a flash image. Combine the profile with the qualified
Runtime source-source broker and its shared NativeAppDataMount dependency,
update the final cohort's native digest/version, and run complete admission.
The two native flags and seven linker wrappers in the supplied profile must
all be selected. The wrappers enforce mount identity and retained flash
custody; the interface alone is insufficient.

Private staging is `/appdata/.risc-file-source` inside Watch's existing 512 KiB
appdata LittleFS partition. At least 64 KiB remains reserved for existing app
data. Files streams at most 4096 bytes per step, draws ordinary progress and
allows Back cancellation. Original files and saved models are never overwritten.
The sealed source survives Files unload, becomes read-only to the selected
receiver, and is removed by Runtime after receiver exit/cancel/error before
fresh Files resumes. A custody-uncertain flash failure deliberately retains
instead of retrying cleanup or releasing radio ownership.

Open is limited by actual remaining private storage, not by a new source API
file-size ceiling. A larger source gets a temporary-storage notice; browsing
and Copy stay usable. Remote HTTP Range-backed streams are not implemented.
They would require Runtime-owned authenticated WebDAV/radio/session custody,
seek/read caching, and receiver-error cancellation after Files unload. Keeping
app-owned transport pointers alive is not a safe substitute.

Host tests exercise actual protocol/controllers/Runtime and the native binding
with pinned LittleFS flash-fault models. Real BLE/Wi-Fi interoperability,
physical flash-full/power interruption and hardware touch/latency still need
Watch/X4 device qualification.
