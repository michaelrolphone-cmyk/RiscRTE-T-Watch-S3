# Crown clock 0.2.2

Separate successor to the preserved 0.1.0 clock image. The user confirmed that
0.1.0 runs on battery after correcting wiring; this is not qualification of the
new sleep path or a power measurement.

The clock now uses a 180-degree deployment rotation (`rotation: 2`, ST7789
MADCTL MX|MY = 0xc0). Logical RGB565 drawing remains 240x240. The panel's
320-row RAM requires address rows 80..319 in this orientation, versus 0..239
without rotation. Both RASET address bytes are transmitted, including rows
256..319. No framebuffer coordinates or clock layout are shifted to compensate. This clock-only
projection has no touch driver, so no inconsistent touch coordinates are exposed.
A future touch-enabled projection must apply the matching transform.

A completed short crown press runs the copied ripple transition, waits for all
accepted presentation work, then prepares panel and PMU. Panel preparation
refuses held frames and pending work, disables PWM backlight, issues display-off
and sleep-in, and waits 120 ms. ALDO3 stays supplied. PMU preparation snapshots
IRQ enables 0x40..0x42, masks everything except short-press 0x41 bit3, clears
latched IRQs, and requires an inactive IRQ with no new key events for 50 ms.
Falling-only key events represent a held key and prohibit preparation. Existing
charge settings and CPU/RTC/display supply voltages are not changed.

The PMU calls the generic GPIO bank sleep extension using its existing IRQ
claim. The bank checks input ownership and translates that public token to its
private CPU-port token. No GPIO number or raw token reaches the app. CPU light
sleep preserves the mapped app, graph and RTC. Each return, including refusal or
partial preparation, resumes PMU then panel. Resume is idempotent; failed restore
retains state for retry and exits the app rather than continuing normal drawing.
RETAINED from the CPU port also terminates this invocation. Presentation waits
are bounded at 10 seconds; peripheral transactions remain bounded. Time asleep
intentionally has no timeout. No driver teardown, deep sleep, reset, or RTC write
is used to implement wake.

The PMU extension retains the existing battery/key prefix and appends
prepare_sleep, resume and light_sleep. The panel extension retains the complete
canonical display.output@1 prefix and appends prepare_sleep/resume. Both are
Watch-local, serialized owner interfaces; callers check full struct_size and all
callbacks. Partial preparation must always be followed by resume. GPIO's shared
append-only extension and result layout come byte-for-byte from RiscRTE revision
dd7993308cf170feeb4a5883eba8857dc6243c8e; sdk/SOURCES.json pins hashes. Older base
GPIO consumers retain prefix-size checks; only sleep use requires the extension.

Boot and every successful wake show the actual T5 ink sweep, forming logo blocks,
wordmark unfolding and loading dots. The original 16-scan curling screen-clearing
field supplies transitions; its precomputed arrival map is resampled into square
portrait coordinates, and EPD black/white commands become RGB565 colors. These
use light foreground on a black background; the existing dark clock palette is
unchanged. The hardware inversion command remains the panel-required setting.
These are app-side visual copies, not a display abstraction change. Exact source,
licenses and reproducible map generator are in apps/clock/effects. Button events
during animation and the first 250 ms after it are drained to avoid immediate
resleep from a wake event. Hardware still supplies its own long-press power-off
behavior; the app does not reinterpret long presses.

## Display regression corrections

The 0.2.0 image changed MADCTL without changing its visible RAM window. The
missing 80-row offset explains the shifted image and unwritten one-third band
reported on hardware. The driver now pairs rotation with the manufacturer's RAM
gap and uses full 16-bit row addresses.

The old provider transferred only one of 240 rows on each runtime poll, plus a
separate completion poll. The provider now drains rows within the caller's
elapsed-time budget (at most 20 ms), passes only the remaining timeout to each
transaction, and caps a poll at 32 rows even if the clock stops advancing.
A new row requires at least the original 2 ms allowance and its calculated wire
time; a 1 ms remainder is not used with the backend's coarse-millisecond deadline. A
completed final row publishes completion in that poll.
The ripple selects its 16 scans by elapsed time and skips obsolete scans if a
frame is slow; its final black frame still completes before sleep. This removes
the compulsory sixteen slow transfers without extending the runtime poll budget.
The panel programs CASET/RASET and RAMWR once per frame, then streams the 240
480-byte rows into that window. Every row ends its SPI transaction and releases
chip select; no shared bus lease spans a runtime yield. The controller's documented
byte-aligned data-pause behavior retains its frame-memory pointer across these
pauses. A new frame resets its window, and any failed transfer/end stops that
presentation rather than blindly continuing. This reduces one frame from 1,440
SPI exchange calls to 245 while retaining the same row/poll/deadline bounds.
Actual physical frame rate still needs measurement.

## 0.2.2 LCD throughput correction

Hardware feedback confirmed the 0.2.1 address correction but still found low frame
rate and skipped animation phases. The remaining limits were the 10 MHz software
SPI ceiling, a 2 ms runtime provider quantum, duplicate runtime waits, and an
unconditional 20 ms wait after each completed app frame. The paired correction
uses an 8 ms maximum generic provider quantum within a 10 ms aggregate budget,
one scheduler wait, and only the remaining part of the app's 20 ms frame interval.
This changes complete-frame throughput, rather than merely hiding late frames.

Only the clock deployment's selected display SPI bus is projected to 40 MHz.
The eight source physical profiles remain unchanged at 10 MHz; no radio or IMU
variant is selected. The exact manufacturer's T-Watch-S3 ST7789 setup below
specifies 40 MHz with the same 240x240 geometry and display pins. Panel 0.3.2
explicitly admits up to 40 MHz, while ordinary Watch SPI drivers retain their
10 MHz limit and Watch I2C retains its 400 kHz limit. Local schema provenance
records this derivation, preserving the upstream schema identity and C ABI.
Board baseline 1.0.1 versions the changed schema/manifests.

The 0.2.2 store requires RiscRTE firmware 0.1.2 at exact source
`a3d23da9cdc1b3a66c6429f29781856fa7fc8f75`, recorded in
`apps/clock/runtime-requirements.json` and each deployment record. The previous
3d0ae01065c00d4f7285dd0a4433a1326125ed10 runtime rejects its 40 MHz bus and must not
be reused with this store. The combined deliverable records the exact runtime
and Watch source commits; the app SDK layout is unchanged.

A deadline-aware host regression executes the production panel/provider code,
including all 245 exchanges and 115,200 pixel bytes. With explicit transport
costs of 0/100/250 microseconds per exchange, old-policy frames take approximately
460/585/765 ms and corrected-policy frames 31/56/96 ms. These controlled test
scenarios are not measurements of a physical watch and do not establish a
hardware frame-rate guarantee.

## Primary sources

- [LILYGO schematic, 2025-03-24](https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43/schematic/T_WATCH-S3%2025-03-24.pdf): SW7 Power Key connects PWR_KEY to AXP2101 PWRON; PMU_IRQ1 routes to GPIO21. No rotary encoder channels were established.
- [ST7789V3 datasheet v0.1, sections 8.5 and 8.6](https://files.waveshare.com/upload/c/c1/ST7789V3_V0.1.pdf#page=59): frame-memory writes pause at completed bytes when chip select is released and continue from the retained pointer; these modes apply to serial and parallel interfaces.
- [Manufacturer T-Watch-S3 TFT setup, pinned commit 9884d6](https://github.com/Xinyuan-LilyGO/TTGO_TWatch_Library/blob/9884d62113cd2f7aa77cd179c346b9017eb08301/extras/Setup212_LilyGo_T_Watch_S3.h): ST7789_DRIVER, 240x240, matching pins and SPI_FREQUENCY 40000000; exact Git blob 3273ca23cc7016b4fd210eb0711ba891a823e7bb.
- [LILYGO display rotation](https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43/src/display/LilyGoDispInterface.cpp#L717-L741): mirror(true,true) pairs with the 80-row RAM gap; mirror(false,false) pairs with zero gap. Its rotation labels use a different baseline from the Watch package.
- [LILYGO Watch initialization and lightSleep](https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43/src/LilyGoWatchS3.cpp): power-key wake uses PMU_INT, short-press IRQ, display sleep, and retained display/touch supply.
- [AXP2101 datasheet v1.4](https://github.com/lewisxhe/XPowersLib/blob/d6997586e68f65afd51baa775903df930db39821/datasheet/AXP2101_Datasheet_V1.4_en.pdf): PWRON events, IRQ enables/status and write-one-to-clear semantics.
- [Copied T5 startup animation](https://github.com/michaelrolphone-cmyk/T5S3-Reader/blob/3d9bc4f373679f5ae8dd184db6a8d0afa5a40231/src/components/StartupScreen.cpp) and [spatial scrub](https://github.com/michaelrolphone-cmyk/T5S3-Reader/blob/3d9bc4f373679f5ae8dd184db6a8d0afa5a40231/src/native/NativeVideoBootScrub.h).

## Verification and next work

Host tests exercise real app/driver code, repeated wake, refused sleep, partial
preparation, retained/error paths and cleanup. Display tests decode actual wire
CASET/RASET/RAMWR data for both orientations, verify every RAM row including
addresses above 255, and exercise row caps, elapsed budgets, remaining SPI
timeouts, final-row completion and failed-transfer stopping. Streaming checks
cover a single exact frame window, chip-select release after every row, subsequent
frame reset and failure recovery without retained bus ownership. App tests include
asynchronous 2-second frames, obsolete-scan skipping and uptime wraparound;
effects tests require a black background, light ink and a final black scrub. Target ELFs and merged image
contents are checked separately. Physical crown behavior, orientation, repeated
wake and current draw remain pending user testing of this successor image.

After delivery: resume shared Springboard and Settings work (time/timezone/time
format/orientation), correct touch transforms, shared Font Awesome icons and
verified navigation inputs. Do not assign rotary pins without hardware evidence.


## NOVA-7 clock 0.3.0

The supplied NOVA face is now the crown clock's production renderer. It defaults
to 12-hour time with AM/PM. RTC fields are displayed as supplied; this app does
not infer a timezone or claim synchronization. Failed or invalid readings show
TIME UNSET. The PMU currently reports percent 255 with PROFILE_MISSING, so the
face honestly shows --%; a future valid 0% remains distinct from unknown.

The face renders on every paced iteration, independently of RTC sampling. A
frame's rendering/presentation time counts toward the existing 20 ms interval;
no extra sleep is added when that interval is already spent. RTC is sampled at
most every 100 ms. An observed second change anchors its fractional phase, with
up to one sampling interval of observation delay; civil time is never advanced
from uptime. Battery is sampled at most every five seconds. Both cached states
are invalidated after a sleep attempt/restoration. Crown key checks still occur
between frames, and outgoing ripple frames use the same NOVA state.

The immutable glyph masks are checked in. Normal target builds neither download
fonts nor run a rasterizer. Both SIL OFL licenses and font source provenance are
included under licenses/nova in every variant and common deployment ZIP. The
common store still contains exactly 14 files; licenses are outside the SPIFFS
store. See apps/clock/nova/README.md for renderer/source details and host checks.

This release retains the 40 MHz projection, corrected 80-row window and streaming
panel 0.3.2 from clock 0.2.2, and requires the exact RiscRTE 0.1.2 source
a3d23da9cdc1b3a66c6429f29781856fa7fc8f75. Complete-frame timing regressions are
host models, and neither those nor renderer CPU timings are measured watch FPS.
