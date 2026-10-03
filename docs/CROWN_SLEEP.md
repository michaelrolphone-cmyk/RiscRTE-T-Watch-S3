# Crown clock 0.2.1

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
completed final row publishes completion in that poll. SPI frequency is unchanged.
The ripple selects its 16 scans by elapsed time and skips obsolete scans if a
frame is slow; its final black frame still completes before sleep. This removes
the compulsory sixteen slow transfers without extending the runtime poll budget.
Actual physical frame rate still needs measurement.

## Primary sources

- [LILYGO schematic, 2025-03-24](https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43/schematic/T_WATCH-S3%2025-03-24.pdf): SW7 Power Key connects PWR_KEY to AXP2101 PWRON; PMU_IRQ1 routes to GPIO21. No rotary encoder channels were established.
- [LILYGO display rotation](https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43/src/display/LilyGoDispInterface.cpp#L717-L741): mirror(true,true) pairs with the 80-row RAM gap; mirror(false,false) pairs with zero gap. Its rotation labels use a different baseline from the Watch package.
- [LILYGO Watch initialization and lightSleep](https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43/src/LilyGoWatchS3.cpp): power-key wake uses PMU_INT, short-press IRQ, display sleep, and retained display/touch supply.
- [AXP2101 datasheet v1.4](https://github.com/lewisxhe/XPowersLib/blob/d6997586e68f65afd51baa775903df930db39821/datasheet/AXP2101_Datasheet_V1.4_en.pdf): PWRON events, IRQ enables/status and write-one-to-clear semantics.
- [Copied T5 startup animation](https://github.com/michaelrolphone-cmyk/T5S3-Reader/blob/3d9bc4f373679f5ae8dd184db6a8d0afa5a40231/src/components/StartupScreen.cpp) and [spatial scrub](https://github.com/michaelrolphone-cmyk/T5S3-Reader/blob/3d9bc4f373679f5ae8dd184db6a8d0afa5a40231/src/native/NativeVideoBootScrub.h).

## Verification and next work

Host tests exercise real app/driver code, repeated wake, refused sleep, partial
preparation, retained/error paths and cleanup. Display tests decode actual wire
CASET/RASET/RAMWR data for both orientations, verify every RAM row including
addresses above 255, and exercise row caps, elapsed budgets, remaining SPI
timeouts, final-row completion and failed-transfer stopping. App tests include
asynchronous 2-second frames, obsolete-scan skipping and uptime wraparound;
effects tests require a black background, light ink and a final black scrub. Target ELFs and merged image
contents are checked separately. Physical crown behavior, orientation, repeated
wake and current draw remain pending user testing of this successor image.

After delivery: resume shared Springboard and Settings work (time/timezone/time
format/orientation), correct touch transforms, shared Font Awesome icons and
verified navigation inputs. Do not assign rotary pins without hardware evidence.
