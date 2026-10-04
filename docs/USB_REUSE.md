# Reader USB input reuse on the original T-Watch-S3

## Current result and boundary

This slice builds the existing Reader host and input providers unchanged and
runs them through the actual minimal runtime provider graph. It adds no device
activation, Watch UI, power writes, firmware USB proxy or replacement decoder.
It does not supply an activatable USB Watch image. Existing GUI/sleep candidates
and package versions remain unchanged.

Source pins are in `tests/usb-reuse-sources.json`:

- [Reader d066f6c7](https://github.com/michaelrolphone-cmyk/T5S3-Reader/tree/d066f6c7373178986f98e02d885f572a3f4949ed)
- [Minimal runtime 0.1.6 / 8609fb92](https://github.com/michaelrolphone-cmyk/RiscRTE/tree/8609fb92ee56ad1c6fb0417051c3fc9796c0edca)

The supplied older local Reader reference has the same selected driver sources,
SDK and builders. Its local-only head is deliberately not used as a CI pin.

## Exact reuse map

| Existing package | Version | Reuse / remaining work |
| --- | --- | --- |
| usb-controller-esp32s3 | 0.1.20 | Keep real PIC IDF USB/PHY/HAL implementation, role selection, external-VBUS lease, bounded DMA/IRQ teardown. Privileged admission, port ownership and Watch power dependency remain missing. This slice does not target-build or activate it. |
| usb-host-v2 | 0.1.5 | Unchanged enumeration publication, generation tokens, interface arbitration and authorized transfers. |
| usb-hid | 0.1.2 | Unchanged descriptor/report transport. |
| usb-hid-keyboard | 0.1.1 | Unchanged ordered, bounded keyboard events; do not coalesce text as gamepad state. |
| usb-hid-gamepad | 0.1.4 | Unchanged descriptor parsing and latest-state mailbox. Requires platform.clock@1. |
| usb-xinput-gamepad | 0.1.3 | Unchanged XInput interface matching, reports and latest state. Requires platform.clock@1. |
| usb-hid-text-input | 0.1.0 | Unchanged input.text@1 conversion. |
| usb-ui-navigation | 0.1.2 | Unchanged input.navigation@1 composition and foreground ownership. External Watch apps still need to consume it. |
| t5s3-usb-power-profile | 0.1.1 | **Do not install for Watch.** It configures BQ25896 wiring/power; Watch has AXP2101 and cannot source connector power. |

The canonical RiscProviderV2.h and RiscPlatformClockV1.h match the minimal runtime
byte-for-byte. The seven ordinary host/input ELFs need only memcpy/memset in the
local Xtensa audit build. No USB implementation imports, new class protocols,
stream service, package-signing system or firmware hardware bridge is needed by
these seven providers. Controller availability is a separate requirement.

The minimal runtime limits the selected graph to 16 providers. The existing
seven-provider launcher closure plus these seven classes, the controller and
one power adapter would total 16. Do not blindly increase capacity or include
unrelated radio/audio/USB classes. Exact future deployment selection must still
be checked against the final Watch closure.

## Manufacturer evidence: role and power

The [pinned LilyGoLib hardware page, section 1 Overview](https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/92f2ac3f90944edd4c1ba293d4a4ca8d3f524e43/docs/hardware/lilygo-t-watch-s3.md)
labels Micro-USB as used for charging/programming and says it “cannot supply
power to external devices”. Its electrical table lists a 3.9–6 V connector input,
not a VBUS source or a qualified USB host supply. Do not convert that input range
into a claim of valid USB peripheral voltage.

The manufacturer wiki links [TTGO schematic at 9884d621, sheets 1–2](https://github.com/Xinyuan-LilyGO/TTGO_TWatch_Library/blob/9884d62113cd2f7aa77cd179c346b9017eb08301/schematic/T_WATCH_S3.pdf).
Visual inspection shows:

- J3 pin 1 VBUS feeds the AXP2101 VBUS input (pin 37), with capacitors/ESD.
- D+ passes R44 10 ohms to DP/GPIO20; D- passes R45 10 ohms to DM/GPIO19.
- J3 ID is unconnected. There is no drawn connector VBUS source/boost switch.
- The file has legacy 2021/V1.4 title-block information and a GPS sheet. It does
  not identify the owner's actual PCB revision or prove a fitted GPS receiver.

The [manufacturer USB configuration](https://wiki.lilygo.cc/products/t-watch-series/t-watch-s3/)
uses hardware CDC on boot, QIO 16 MB flash and OPI PSRAM. The present runtime uses
that native USB route for programming/diagnostics. Internal USB Serial/JTAG and
OTG share the PHY; host takeover interrupts that device-mode connection. The
existing Reader controller captures/restores the route, but this does not by
itself grant exclusive ownership against the minimal runtime diagnostic sink.

An externally powered, explicitly qualified host-data topology is needed for a
bus-powered keyboard/controller. A powered hub alone is not proof: compliant
upstream ports do not normally source upstream VBUS, and unwanted upstream
backfeed is a hazard. Do not connect two USB hosts or assume an arbitrary Y-cable
is safe. No cable purchase, electrical test or board power change is part of this
software slice. Unknown voltage/topology must fail closed, without battery boost.

## Remaining integration, with ownership

1. **Generic runtime, separate increment:** enable the existing verified
   privileged provider route under independent admission and opaque resource
   policy. The 46-symbol CPU ABI1 inventory is already identical; the current
   `ModuleV2::loadVerifiedBytes` deliberately returns false. Do not widen ordinary
   exports. See the bounded proposal below.
2. **Existing AXP2101 owner, separate Watch change:** add read-only incoming-VBUS,
   voltage and fault observations through its existing I2C claim. A small
   composition provider can publish canonical board.power.vbus@1 and always
   reject acquire_host with a zero lease. Only an explicitly configured,
   electrically qualified external topology may expose acquire_external_host.
   It must enforce fresh observations, bounded settling and retained cleanup.
   It must not claim address 0x34 independently or change charging/rails.
3. **CPU port plus existing controller:** establish exclusive opaque resource
   ownership for the shared PHY/diagnostic path. Preserve host-role/client/DMA
   preparation before the power lease and detector enable; preserve failed
   teardown ownership and safe console handback. No resident USB host code.
4. **External Watch app policy:** subscribe to canonical input.text/navigation
   and HID/XInput capabilities using normal grants; coordinate sleep with active
   USB ownership. No app-specific controller resets, PMU register access or
   changes to the present crown/display/shared-I2C behavior.

Any eventual changed distributable gets its own strictly increased version.
Unchanged reused sources keep their canonical identities/versions. This
build/test/documentation-only slice changes no distributable payload.

## Bounded generic admission proposal (not implemented here)

Reserve the next generic increment separately from runtime 0.1.6/0.1.7 work.
Lift the reviewed Reader path at the pin rather than introducing another loader:

- `DeviceProviderExecutorV2::registerManagerValidated` and private graph admission
  own bounded identity, dependencies, exact declared imports and image bytes.
  Keep `GraphV2::addVerified` nonprivileged and reject forged privilege flags.
- Adapt `ModuleV2::loadVerifiedBytes`'s snapshot, digest, structural validation,
  exact relocation and entrypoint/lifetime path to the minimal boot-store owner.
  Reuse the existing private ABI1 relocation functions already present. Do not
  import Reader's board-ID-specific transitional I2C/SPI exceptions, package
  storage cache or unrelated ABI2/3 display extensions.
- The trusted bootstrap executor must require a separate, default-deny runtime
  policy grant for the exact module generation and selected CPU ABI/resources.
  A manifest, capability string, installed file or matching checksum alone must
  never authorize privileged relocation. The policy representation and opaque
  resource handoff need review before implementation. No signing prerequisite.
- Validate the same private snapshot that gets mapped; keep exact sorted import
  equality across both .dynsym and .symtab, 128-import/8-MiB bounds, structural
  relocation checks and the unchanged ABI1 inventory. Preserve owner-task scope,
  per-module one-shot admission, nested-load exclusion and no custom-resolver,
  registered-symbol or ordinary-loader fallback.
- Revoke consumer authority first. Failed start/quiescence must pin mapped code,
  image/metadata and lower dependencies until checked retry succeeds; retain
  the current runtime app-exit/sleep barriers and 0.1.7 storage cleanup authority.

Focused checks should execute the real private resolver/relocator and admission
with corrupt images, altered/missing/extra imports, wrong ABI/policy/module/task,
caller-buffer mutation, nested relocation, failure rollback and failed-quiesce
retention. Add an actual pinned IDF controller link/import audit and two
single-job firmware targets (baseline and native-USB). These establish software
behavior, not physical enumeration, backfeed safety or successful HID reports.

## Reproduce the first slice

Check out the exact Reader/runtime pins in separate directories, then run:

```sh
python3 -m unittest discover -s tests -p test_usb_reuse.py -v
python3 scripts/build_reader_usb_reuse.py --reader /path/to/reader \
  --runtime /path/to/runtime --output dist/usb-reuse \
  --cc /path/to/xtensa-esp32s3-elf-gcc
```

Omit --cc for host-only integration. The output must be new: prior evidence is
not overwritten. Source revisions and modified selected files are rejected;
bounded snapshots are extracted from committed bytes. The existing canonical
Reader builders run unchanged against that snapshot. No source tree is patched.

The host graph uses a clearly test-only physical-controller table, with the real
seven providers and minimal GraphV2/ModuleV2. It checks missing dependency/wrong
API rejection, quiet polling, text foreground handoff, shared lifetime, revoked
failed-release grants, pinned failed quiescence, retry/fresh generations and
failed event observation. UBSan is enabled by default. It does not simulate or
claim physical USB enumeration/reports. Existing Reader HID/XInput/report tests
remain the decoder evidence.

Target builds check canonical exports, actual imports against minimal runtime
libc, and the actual runtime structural ELF validator with corruption/truncation
negatives. They do not execute Xtensa instructions on the host. CI uses the
existing pinned GCC8.4 toolchain/checksum; the initial local run used GCC14.2,
which is recorded explicitly in each evidence report.
