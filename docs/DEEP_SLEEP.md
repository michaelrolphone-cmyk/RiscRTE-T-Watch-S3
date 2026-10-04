# Watch Hybrid sleep 0.5.2

Fresh Clock and all application idle sleep now enter Light for five asleep minutes,
then enter Deep without a visible wake frame. Apps sleep after one minute idle.
Light wake resumes the same app stack and RAM, including Calculator expressions,
Settings editor drafts and live Stopwatch precision. Deep wake restarts the
normal default Clock. Crown sleeps Clock with the same progression; crown Back
in other apps remains unchanged.

Settings labels its three choices **Clock Sleep Mode**: Light, Deep, and Light
5 min then Deep. Previously saved valid manual Light/Deep records remain valid;
missing/corrupt records default Hybrid without a write. Other apps always use
Hybrid and receive no Settings namespace. Stopwatch retains only namespace 2.

Runtime 0.1.6 supplies owned bounded timer wake. App-side policy accepts only a
successful timer wake for progression, checks both non-acknowledged PMU latched
key bits and physical IRQ before and after dark panel hold, and lets a crown
edge win. Refusals restore the app and restart the one-minute interval; clean
PMU mask restoration preserves the last actually observed released/held latch,
so retry does not require an invented crown event. Unsafe retained cleanup
stops normal I/O and the Runtime barrier pins app/dependencies before fini/unload.

The panel, rails, full-frame transport and touch driver remain unchanged. No
alarm service, provider storage, ULP program or device qualification is included.

## Preserved physical Deep contract from 0.5.0

## Exact mechanism and limits

The reusable B1 mechanism is an owned RTC-capable input with ESP-IDF EXT1 wake
and `esp_deep_sleep_start`. It is **not an ESP32 ULP-coprocessor program**. The
reviewed T5 reference used RTC-retained data plus timer/button deep sleep, not a
ULP program. Deep remains crown-woken; Hybrid adds only the bounded Light timer. RTC alarms,
scheduled apps and vibration/sound policies remain separate application
work. Double-tap wake is deferred; the touch controller's irreversible sleep
register is not written. No promised current draw or battery-life multiplier
is inferred from host tests or API names.

The IRQ is the PMU's existing owned active-low GPIO21 input; no app or firmware
hardcodes that pin for policy. Its requested internal pull-up requires RTC_PERIPH
ON in the pinned IDF implementation. LCD/touch ALDO3 stays powered. PMU charge,
CPU, RTC and rail voltage behavior stays at the accepted baseline. PMU IRQ masks
0x40/0x42 are zero during deep sleep and stay masked on a fresh boot; the existing
boot setup enables only the key bits in 0x41. No prior RAM IRQ snapshot is claimed
to survive reset. This crown-only application does not subscribe to other IRQs.

## Ordered preparation and recovery

Clock releases its touch subscription, drains presentation, dims, and completes
one black frame. The unchanged panel light preparation sends display-off and
sleep-in. Deep preparation then writes backlight statically inactive, stopping
PWM, and retains only that explicitly owned output pad. PWM duty zero alone is
not sufficient: the generic CPU correctly rejects an active PWM resource.

PMU preparation snapshots interrupt enables, arms released short-press IRQ and
waits for a stable inactive line. Its appended terminal callback goes through the
GPIO bank's owned-input token translation into the generic runtime. Successful
entry cannot return. Fresh GPIO claim stages the configured safe initial output
before releasing the old pad hold, and the accepted first-complete-frame gate
controls brightness. All normal panel SPI, rows, offsets, renderer and transition
algorithms remain unchanged.

An ordinary refusal restores PMU, releases the output hold before panel PWM
resume, and paints a complete fresh Clock while dark before relighting. Refusal
restarts the existing idle interval, preventing a busy retry loop. An incomplete
hold/entry/unhold rollback returns RETAINED: no further normal I/O is attempted,
and claims/dependencies remain retained until external restart. Missing deep
suffixes refuse Deep cleanly while preserving the old Light prefix contract.

## Persistence and failure behavior

Clock and Settings still explicitly declare storage.key-value@1 with namespace instance
1. Other bundled apps receive no such grant. The app-owned key `sleep_mode` has a
four-byte versioned record; missing, unknown, malformed or unavailable values
select Hybrid. Runtime stores opaque bounded bytes and knows no Watch mode/key.
Clock only reads; Settings writes only after explicit Save, avoids unchanged
writes and verifies the result. Failed saves display an unconfirmed-save message
and re-read actual storage because an error does not guarantee the old value.

The NVS SDK can hide discarded corruption or some internal errors as NOT_FOUND;
this has the same safe Hybrid fallback. No automatic erase-all/retry, bootfs
writes or storage formatting is introduced. SDK internal recovery metadata may
still change on initialization. Flash power-cut durability is not hardware-tested.
Settings persist across app switches and normal reset/deep wake. The supplied
full merged BIN overwrites the lower 8 MiB, including NVS/settings, when reflashed;
it does not promise settings preservation across that operation.

## Verification

The increment adds real production driver tests for old suffixes, token
translation, static-write/hold/unhold ordering, ordinary refusal, repeated
prepare/resume and retained errors. Clock tests cover manual/60-second entry,
invalid-record fallback, old interfaces, preparation refusal, terminal entry and
three fresh-process boots. Shared Settings tests cover save, cancel, absent
storage, bad records, unchanged saves, failed/uncertain saves and reopen, plus
bounded encoding tests. The complete existing GUI, RTC/DST, resource-lifecycle,
full-frame and transport suites remain required.

The paired runtime has independent grant/namespace/stale-context and NVS fault
checks, including Arduino's actual initialization-recovery erase branch. Its
native retention barrier runs before app finalization, memory reclamation or
unload, and prevents queued/default launches after retained errors. The real
Watch Runtime/Clock/seven-driver integration verifies three terminal fresh
boots, ordinary refusal with clean teardown, and four retained-fault cases
with zero unloads and pinned resources. Exact
source target CI, payload hashes, all eight board-profile projections, SPIFFS
round trips and a source/ELF inventory must pass before delivering the BIN.
These checks are software evidence, not physical wake/current qualification.

### Immutable RTC metadata custody

GCC8.4 can renumber the RTC's compiler-generated local `days$NNNN` symbol after
unrelated header declarations are added. The build checks the single 12-byte
calendar object and may normalize only its equal-length name in the non-allocated
`.strtab`, outside every PT_LOAD range. The resulting **entire ELF** must hash
exactly to the physically accepted RTC0.2.0 artifact; any other byte change fails.
Raw compiled bytes and a before/after proof accompany CI. The deployed RTC bytes,
code, relocations, data and package identity remain exact baseline bytes.
