# Implemented consumers and required runtime backfill

These packages implement peripheral protocols. They do **not** implement a
T-Watch RiscRTE CPU/firmware port. A successful software build is not successful
loading or hardware qualification. No fallback to firmware peripheral helpers,
Wire, Arduino global SPI, GPIO MMIO, unclocked audio or busy-loop IR remains.

## Canonical versus proposed ABI

Canonical Reader snapshot:
`T5S3-Reader@3d9bc4f373679f5ae8dd184db6a8d0afa5a40231`. Provider v2, stream suffix,
clock, I2C, display, raw touch and navigation headers are byte-for-byte copies.
Their hashes and exact source pins are in [SDK sources](../sdk/SOURCES.json).
The raw GPIO/SPI/radio proposals are copied unchanged from Garden
`1f7fb82efec08cf8751057d84e707f20be2fb7a5`; the shared hardware mapping header,
contract and common schema are aligned to
`7e30afc407c86f34364cbfa2035d6f7893fdea8c` (comments/schema only, same C layout). These are proposals with
implemented consumers, **not existing Reader services**.

`RiscGpioBankV1.h` and `RiscBatteryGaugeV1.h` were local watch contracts in the
baseline; their names do not establish canonical Reader support. The watch GPIO
adapter preserves `gpio.bank@1` for existing device consumers, while raw claims
use the shared `platform.gpio@1` owner. `board.battery@1` preserves its original
prefix and appends PMIC key events. Future upstream adoption must match the
header, including struct_size checks, or provide a separately versioned adapter.

## Exact mapping/instance contract

[Shared mapping specification](HARDWARE_MAPPING.md) and
[RiscHardwareConfigV1.h](../sdk/driver/RiscHardwareConfigV1.h) define
`platform.board@2`, `hardware.catalog@1`, and `hardware.device@1`.
The board package selects a catalog only when the authorized board/revision
matches an explicit profile. No implicit default exists. The generic runtime
must schema-validate it, select a compatible driver, materialize the exact typed
C config and scope dependency tables to the named instance IDs. Package presence
or metadata filtering is not hardware authorization.

Each physical entry gets **independent ELF data/BSS and dependency contexts**.
The same `twatch-i2c` image is mapped twice for controllers0 and1; re-starting one
singleton descriptor for a different device is forbidden. A driver-manager
compatible-hardware filter, module instantiation, config injection, per-instance
resolver and resource arbitration are future Reader work, not supplied here.

Both schemas apply the optional-reset clarification recorded in
[SCHEMA_PROVENANCE.json](SCHEMA_PROVENANCE.json); the original upstream hash is retained. The
[T-Watch extension schema](twatch-board-v1.schema.json) registers controller.gpio,
controller.i2c, peripheral.i2c, power.axp2101, audio.i2s and radio.lora. Absent display/touch reset (`-1`) requires both reset delays zero; present
reset requires positive bounded delays. Array counts and reserved-zero fields are generated
by the materializer, not independently trusted JSON values. `power.axp2101` has
the whole config size in its nested `device.struct_size`. Other exact layouts
are in [TWatchHardwareV1.h](../sdk/driver/TWatchHardwareV1.h).

`controller.gpio` uses `tw_hw_gpio_controller_v1`: struct_size, unit0,
features0. Shared reserved richer types such as `audio.i2s-port` are distinct
and are not reinterpreted as `audio.i2s`.

Target ABI is ordinary unpacked C on little-endian32-bit Xtensa. All API tables
begin uint32 version/size, then context at offset8 and callbacks at offset12.
The hardware envelope is40 bytes, config pointer offset36; bus record40 bytes;
I2C device config56 bytes; audio config16 bytes. Driver descriptor36 bytes,
quiesce offset32, canonical polling descriptor48 bytes. Target assertions are in
[abi.c](../tests/abi.c); native host pointer sizes intentionally differ.

## Raw port contracts to supply

The full declarations in [GardenPlatformV1.h](../sdk/driver/GardenPlatformV1.h)
and [TWatchPlatformV1.h](../sdk/driver/TWatchPlatformV1.h) are authoritative. All
callbacks below are required; missing/null/wrong-version/truncated or duplicate
matching dependencies fail activation. Larger append-only tables are accepted.

| Capability | Exact table / callbacks after header and context | Required behavior |
|---|---|---|
| `platform.clock@1` | canonical `risc_platform_clock_api_v1`: monotonic_ms, sleep_ms | monotonic64-bit milliseconds; sleep genuinely yields; no peripheral policy |
| `platform.gpio@1` | `garden_gpio_v1`: claim(pin,output,initial,pullup,&token), write, read, pwm, release, waveform | one global pin owner, latch before output enable; bounded1ms operations except waveform; write cancels PWM; waveform semantics identical to finalized Garden proposal |
| `spi.bus@1` | `garden_spi_v1`: claim(sclk,mosi,miso,cs,&token), begin(hz,mode,timeout), exchange, end, idle_clocks, release | one ELF/raw-controller owner per physical SPI controller; same bus signals may share distinct CS. Scoped context selects SPI2 or SPI3, not arbitrary registry ordering. Mode0/MSB-first, max512 bytes/exchange; begin holds a single total deadline/CS across exchanges; NULL tx sends0xff. end drains and deasserts CS; false retains transaction for retry |
| `platform.i2c.controller@1` | `twatch_i2c_controller_v1`: open(controller,sda,scl,hz,&token), transfer(token,address,tx,tn,rx,rn,timeout), close | controller0/1, open-drain pads with pullups, clock stretch/NACK/arbitration handling; combined write/read repeated START; one admission+transfer deadline. No per-device protocol. Transfer phases<=512 bytes, timeout1–1000ms. close drains callbacks/controller and relinquishes pads only on success |
| `platform.i2s.controller@1` | `twatch_i2s_controller_v1`: open(controller,pdm_rx,clock_pin,ws_pin,data_pin,rate,channels,&token), write, read, close | clocked Philips I2S TX or PDM RX; DMA/controller/pins jointly owned. I2S0 required for S3 PDM; board uses I2S1 stereo TX. Signed16 native-endian PCM, max256 frames/call; caller buffer copied before return; actual partial count<=request,40ms total transfer limit. close stops/drains DMA and drives outputs safe before release; failure preserves token |
| `platform.carrier@1` | `twatch_carrier_v1`: claim(pin,&token), send(token,hz,durations_us,count), idle, release | raw gated33%-duty hardware carrier,20–56kHz; alternating mark/space starting mark, odd count<=128, all durations positive,total<=150ms. Synchronous bounded completion with scheduler cooperation, no retained pointer; ends LOW on success/error. idle must abort/drain; failed release preserves token |
| `platform.radio@1` | identical `garden_radio_v1`: claim, join, state, leave, release, start_ap, stop_ap, addresses | CPU Wi-Fi stack session and RF coexistence owner; station/AP coexist; bounded copied credentials; join acceptance is not connected. Same state0/1/2 and network-order IPv4 arrays as Garden. APIs20ms except stop/drain100ms; failed release retains token |
| `platform.hci.controller@1` | `twatch_hci_controller_v1`: open(unit,&token), send(token,type,packet,n,timeout), receive(token,&type,packet,capacity,&n,timeout), close | ESP32-S3 BLE controller HCI, no host/GATT logic; exclusive unit0 session, coordinate RF coexistence with Wi-Fi. H4 type byte separate from standard payload header. send<=1028 bytes,total20ms; receive timeout0 is nonblocking, copies one packet or length0. close drains controller/callbacks before freeing and is bounded100ms; failure retains token |

Every raw claim/open initializes output token to zero and leaves no hardware
changes on false. Tokens are nonzero, monotonically generated and never reused
within a mapped generation. Failed `release`/`close`/SPI `end` retain ownership.
Global arbitration covers GPIO, buses, PWM, RMT/carrier, I2S, DMA and USB; a
manifest validator alone cannot enforce hardware ownership. No raw provider
retains synchronous caller pointers. Read/write/transfer failures are real
failures, never success with fabricated data. Synchronous I/O waits yield and
terminate on deadline, including lock admission; a timeout is not restarted for
each transfer phase. Grant revocation blocks new work, but dependency tables and
ELF memory remain pinned through failed start and failed quiescence.

## Implemented device APIs and lifetimes

[Local device declarations](../include/twatch_caps.h) specify callback order and
fixed scalar layouts. APIs are called on one grant-owning executor unless their
contract below explicitly provides its own lock. No unsynchronized cross-task
calling or ISR invocation is supported by the local RTC/motion/haptic/audio/IR/
radio/battery/GPIO tables. Failed partial activation must be followed by repeated
quiesce before unmapping, not by another start. Nonzero claims block restart.

| Published capability | Behavior and bounds |
|---|---|
| `gpio.bank@1` | preserves original claim/write/read/release table;48 leases, monotonic public tokens; unsupported pulldown/open-drain flags reject. I2C no longer uses GPIO bit-banging |
| `i2c.bus@1` | canonical8-address token owner, atomic try-lock over whole transaction; device release cannot race an active call; configured controller closes only after all address leases end. No token0 release |
| `board.battery@1` | millivolts and read-only AXP2101 SOC estimate0..100 when documented admission checks pass; percent255=unavailable (legacy PROFILE_MISSING flag). See PMU_BATTERY.md for guards and accuracy limits. Charging bit from PMIC status[6:5]. `twatch_pmu_api_v1` appends key_events; bits0=long and1=short from IRQ register0x49, ACK only0x0c. Check struct_size before suffix use. ID/rail bounds/100mA readback required. Up to4 configured ALDO/BLDO rails, indices0..5=ALDO1..4/BLDO1..2. Restore original rail voltage/enables and key-IRQ enables on teardown; keep100mA charge ceiling. DC1/backup/charge voltage untouched |
| `display.output@1` | canonical240x240 RGB565, one115200-byte retained frame; submit nonblocking, frame lease consumed; one latest monotonic present token. One480-byte row per poll; damage validated then conservatively full-frame. FIFO only. Native RGB565 becomes MSB-first wire. PWM brightness. Atomic try-lock; client serializes frame lease calls. quiesce cancels queued transfer because all raw operations drain before each poll returns; held user frame still blocks unload |
| `input.touch.raw@1` | canonical four subscribers/32-slot ring each, hardware contact IDs, two contacts. One coherent13-byte report per poll (regardless of larger budget), no reliance on a latched IRQ edge. Atomic try-lock over I/O and state. Invalid report/overflow yields GAP; transient read error preserves unread events. Subscriptions block quiesce; all must unsubscribe |
| `motion.accel@1` | read XYZ and chip_id;100Hz/±4g configured; signed16-bit raw register representation, not calibrated SI units. Reject observed ID outside explicit profile. Stop acceleration before release. Feature firmware, step counting, gesture algorithms and FIFO are not advertised |
| `rtc.clock@2` | read/write valid calendar2000–2099, valid BCD,weekday0–6; VL/century fail. alarm(minute,hour,day,weekday,enable),255 disables a compare; alarm_pending(&pending,ack). Reads/writes stop on I/O errors. Disable alarm output before releasing; clock keeps running; clock-out disabled |
| `haptic.effect@1` | effect1–123, library1, internal trigger, waveform[1]=0 terminator; stop clears GO; teardown must successfully stop before release. No invented motor calibration/rated-voltage setting |
| `input.navigation@1` | GPIO key maps to BACK;30ms board-configured debounce; neutral rearm after reset/foreground changes. Matching foreground navigation grant suppresses it; invalid foreground request remains suppressed |
| `radio.lora@2` | configure explicit frequency/BW/SF/CR/power/preamble; CRC-on explicit-header normal-IQ packets<=255 bytes. SX1262 BW125/250/500kHz,power−9..22dBm; SX1280 BW203125/406250/812500/1625000Hz,power−18..13dBm;SF5–12,CR5–8,preamble8–4096. send/receive start asynchronous radio work with1–60000ms timeout; poll reads IRQ/result and performs bounded SPI; read consumes received packet only if capacity suffices; cancel enters standby/clears IRQ. TX/RX cannot overlap. Timeout/CRC states distinguished; I/O false preserves ownership for cancel/retry. GPIO BUSY each wait<=20ms with1ms yields; configure has a fixed bounded command count; all raw transfers<=20ms. Reset asserted before releasing after any failure. No LoRaWAN/FSK/ranging/CC1101 protocol claimed |
| `audio.output@1` |8/16/22.05/44.1kHz mono/stereo s16,1..256 frames/write; mono duplicated after one gain application. Gain0..maximum,no amplification. False may follow a partial hardware write; do not blindly resend as if atomic. silence writes32 zero frames; close drains transport |
| `audio.input@1` |8/16kHz mono PDM-converted s16,1..256 frames/read; *got valid on partial/error,never exceeds capacity. level is mean absolute sample amplitude of last read, despite inherited parameter name `rms_out`; no calibrated acoustic claim |
| `ir.transmit@1` | standard NEC8 plus complements or NEC32 LSB-first;67 mark/space durations, raw limits above; no IR receiver |
| `net.wifi@1` | exact Garden table including AP/address suffix, same stable package ID`wifi`; SSID1–32,password<=63,AP WPA requires8–63 or explicit empty/open. Source and behavior reused rather than watch-only implementation |
| `bluetooth.hci@1` | [RiscBluetoothHciV1.h](../sdk/driver/RiscBluetoothHciV1.h): send and next; validates HCI command3+length,ACL4+length; rejects unsupported packet types. next requires1028-byte capacity and returns1 packet,0 empty,−1 error/malformed. Receives event or ACL only. No Bluetooth host/GATT/paired-device manager claimed |

`bool=false` denotes invalid input, unavailable/closing provider, contention or
transport failure; no distinction is invented where the existing ABI cannot
carry it. Touch has canonical −2 fault/−1 stale-or-gap/0 empty/1 event codes;
HCI has its own documented−1/0/1 codes. LoRa status state constants are exactly
those in the header. Caller-owned outputs are usable only as stated above.
All local capability contexts are private to an independently mapped ELF instance.

## Integration order and remaining firmware couplings

1. Add independent ELF instantiation, typed hardware config materialization,
   compatible/revision filtering and dependency scoping. Validate schemas,
   unknown fields, identity lengths<=96/no embedded NUL, array bounds, unique
   IDs/address/pins and acyclic dependencies. Do not convert arbitrary JSON into
   a C pointer or bind the first installed I2C provider.
2. Install board-correct raw controller providers with global resource policy.
   Canonical Reader I2C compatibility driver currently assumes Reader wiring;
   it must not be substituted for this configured watch bus owner.
3. Port clock/heap/PSRAM/flash module store, loader relocations and libc exports.
   The only undefined imports accepted here are memcpy/memset/strcmp/strlen.
   Display requires115200 bytes plus module overhead; catalog is immutable data.
4. Implement I2S/PDM DMA, carrier/RMT, Wi-Fi RF/coexistence and BLE HCI backends.
   Wi-Fi and BLE wrappers do not port Espressif's controller/stack firmware.
5. USB19/20 needs board-authorized role/PHY policy. Reuse existing Reader USB
   controller/class ELFs after their CPU import/power prerequisites are ported;
   do not invent host VBUS on this charge/program connector. Keep boot-only
   flash/PSRAM and recovery ownership distinct from grantable peripheral pins.
6. Filesystem implementations, generic network sockets/DNS/TLS/NTP, BLE host/GATT,
   sleep/wake IRQ delivery, battery profiles and richer sensor features belong in
   the conversion backlog. No shared Reader storage extension is duplicated.
7. Confirm physical variant, RF oscillator/antenna, touch/display orientation,
   motor calibration, electrical timing and safe shutdown on actual hardware in
   a separately authorized session. Software fixtures do not establish those.

The raw controller APIs, schema materializers and device-manager filtering are
**specified, not implemented in Reader by this PR**. No UI/app/default launcher,
watch firmware image, hardware qualification, release or deployment is included.


## Power dependency and SPI namespace integration notes

The DRV2605 haptic manifest binds `board.battery@1` to PMU instance4 as a
startup/shutdown dependency: the selected profile configures BLDO2 (rail5) at
3.3V before haptic activation and keeps it alive until haptic quiescence. The
haptic protocol does not select that rail, and the generic runtime must not
hardcode BLDO2 or watch instance IDs. This dependency currently pins the entire
PMU; it is not a fine-grained rail lease. The same existing PMU dependency model
applies to display/touch/radio. A future generic rail contract requires an
explicit versioned migration, preserving these edges until that migration.

Each SPI bus declares `controller_namespace: riscrte.logical` and an explicit
`physical_controller`: logical0 maps to physical2/SPI2 and logical1 to
physical3/SPI3. I2C buses declare `esp32.peripheral`, retaining physical0/1.
These are not ESP-IDF enum values; the port translates explicitly. No implicit
+2 arithmetic or board-name inference is permitted. Physical-controller keys
must arbitrate aliases together. Bind each external `spi.bus@1` context using the
materialized bus instance (103/104 in these profiles), not package order.
Panel0.2.1 commands, initialization and pixel rows all use the configured bus
frequency, admitted up to10MHz. No command path may silently exceed a slower
board-configured limit.
