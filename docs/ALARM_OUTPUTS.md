# Alarm output prerequisites

`twatch-speaker` and `twatch-haptic` 0.2.1 are source candidates for the assigned
alarm/countdown work. They preserve the existing `audio.output@1` and
`haptic.effect@1` layouts and chip drivers; there is no replacement app. The
stable accepted Watch 1.0.0 product/accepted image, Clock, launcher, PMU, hardware
profiles and previously published 0.2.0 component artifacts are unchanged.

The service uses audio 8000 Hz mono, at most 256 frames per write. The existing
MAX98357A driver scales and duplicates mono to Philips signed16 stereo for the
runtime controller. It keeps a raw cleanup token even when open returns failure.
Partial/failed writes latch an error and refuse further PCM writes until close,
so an accepted fragment cannot be replayed by retrying the original buffer.
Silence is advisory. Close delegates to the raw controller's physical stop and
must succeed independently of a failed silence write or unrelated display DMA.
Failed close retains the stream and quiescence fails without unmapping resources.

The existing DRV2605 ROM-library path uses effect 47 for the service, without
inventing a waveform. Fresh driver start first validates chip identity, then
clears GO before setting internal-trigger mode/library/sequence terminator.
Each new effect also clears GO before changing the sequence. Failed partial
initialization still attempts GO=0 for an identified chip; failed stop retains
the device claim. Unidentified devices receive no configuration writes. Stop is
one bounded 30 ms I2C transaction; an effect performs at most six transactions.
No output cleanup tears down PMU ownership or another provider's bus/rail.

## Integration contract

Select the existing profile's speaker instance 12 and haptic instance 9 with
exact dependencies, including the existing I2C instance 2 and PMU instance 4.
The shared PMU owner must be configured with BLDO2 (`rail id 5`, 3300 mV) before
haptic start. It already supports that rail; no second PMU owner or adapter rail
teardown is introduced. Use the exact selected profile's speaker controller and
BCLK/WS/data pins. Runtime 0.1.8 supplies the generic raw I2S TX prerequisite;
provider storage from Runtime 0.1.7 and external alarm service remain separate
requirements. The integration must stop/close both outputs before sleep or app
exit, keep failures visible, and retain grants when safe stop is not proven.

`python scripts/test_alarm_outputs.py` runs real driver source with ASan/UBSan:
fresh GO clear, each startup/effect failure, retained stop, failed-open token,
partial PCM no replay and silence-independent close. The existing 35 contract
fixtures remain applicable. Native I2S/backend fault tests belong to Runtime.
Host tests/target builds do not qualify physical sound, vibration, deep-sleep
wakeup or power draw. No awake-only alarm or hardware-ready claim is made here.
