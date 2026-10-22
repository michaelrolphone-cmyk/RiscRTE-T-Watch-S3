# Retained Home low-battery composition

This is additive host qualification of the selected Home source in retained
T-Watch 1.1.46. It is stacked on unchanged PR #84
`854f8a1a7d5d6eff0e0585794269bd209dbfde15`. No production source, source pin,
recipe, grant, accepted byte, or pre-existing test changes. There is no release,
installation, device access, or physical radio operation.

## Exact composition

The runner imports the existing artifact/source validation and verifies every
locked release input before extracting the Home canonical compile definitions.
It asserts the exact retained Home artifact identity and replays all 28 `-D`
definitions, including crash namespace 61, `PORTABLE_LOW_BATTERY`,
`WATCH_ATOMIC_PREFERENCES`, `PORTABLE_QUICK_ATOMIC_PREFERENCES`, and
`PORTABLE_PREFERENCE_STORE`.

It executes actual `crown.c` from Watch
`416fa9f144fa5bd5471e6f4c9cefff21455c8361`, `home_automatic.inc` and
`quick_session.c` from System Apps `bb0cadf3cec3445a64e11513b47b2676f3fdd92d`,
and Utilities `4fdcad2495c33fe63f5f6faca9b11ced3c739a5b`. All checkouts must
have their pinned HEAD and no tracked changes. Only the inherited host fixture
is adapted to replace its main and expose its mock runtime table. Production
policy and scheduler sources are never rewritten.

One shared namespace 1 record store backs both Runtime preference operations and
generic-KV reads. Successful copied submissions immediately update those same
bytes; later Home loads cannot accidentally read fixed pre-transition arrays.
Namespace 2 cannot read namespace 1 records. The mock advertises exactly
`COPIED_INPUT=4`, not atomic-group/native-durable flags. Automatic writes require
an explicit `PFA0001` low-battery intention. Generic Home writes are forbidden.

## Ten scenarios, each plain and ASan/UBSan

- Three scheduler scenarios preserve each saved Light, Deep, and Hybrid mode.
  Valid 10% then 9% applies the policy once, persists idle 20s/deep 60s/brightness 15%
  and radio-off records, and observes Wi-Fi disconnect/down plus Bluetooth off.
  The fixture first observes the original radios enabled. It then checks no
  sleep request immediately before the 20s boundary and the real Home scheduler's
  request within 20s..20.25s. The observed synthetic arm/request times are 1/20001ms.
  Light requests untimed Light; Deep requests Deep; Hybrid requests Light for 60s
  and then Deep following the modeled timer wake. All paths receive the selected
  60s value without changing the saved mode.
- Three override scenarios use real serializers to save 120s/420s timers,
  brightness 65%, and Wi-Fi/Bluetooth-enabled preferences after the first
  transition. Reopened Home consumes them, and repeated low samples do not
  overwrite them. Valid 10% rearms only the latch and restores nothing; next 9%
  reapplies the low profile. These are saved-record/inter-invocation boundaries,
  not a live Quick or Settings UI gesture replay.
- The low-latched invalid/charging scenario preserves those same saved overrides
  through charging-flag changes, profile-missing input, out-of-range percentage,
  an absent-battery status, and read refusal. These do not fabricate a rearm.
- The armed-latch invalid-entry scenario directly tests invalid sub-10% inputs
  before any low transition. No setting is written or applied. Charging flags
  change while the valid percentage remains 10% without creating an edge. A later
  valid 9% while charging enters; valid 10% while charging rearms without restoring.
- A partial-write scenario refuses only the deep-timer submission. The edge,
  idle timer, brightness and radio records remain committed; the old 360s deep
  timer remains. Repeated low samples and a new invocation do not retry/replay
  the crossing or falsely report its failed write as confirmed.
- An uncertain-custody scenario commits the copied edge then refuses collection.
  Home retains its token and invocation, halts before further setting writes,
  and a repeated entry performs no more provider I/O or submissions. The current
  source emits two retain notifications while unwinding; this is recorded, not
  rewritten as a single notification.

Total: 20 scenario executions and 50 Home invocations across the two variants.
Wrong-source and each missing required-definition control are rejected.

Charging is not a policy veto. The unchanged source uses valid percentage
thresholds; a charger flag by itself does not fabricate a threshold transition.
Earlier shorthand about charging is not a new acceptance constraint or a request
to suppress a valid 9%% crossing while charging.

## Limits

This proves selected-source composition under the exact feature definitions,
not execution of the retained Xtensa ELF or a new bit-identical source rebuild.
The clock, providers, copied preference transport, and persistent store are host
mocks. This is not native NVS durability, atomic-group behavior, physical 20s
accuracy, physical Wi-Fi/Bluetooth switching, sleep/wake, display/input recovery,
current consumption, or live-memory qualification. Deep requests return a modeled
refusal so cleanup can be inspected. LeakSanitizer is disabled; ASan and UBSan
are enabled for the sanitized runs.

The retained factory image still erases saved data. No preserving installation
route, release, merge, deployment, device action, or hardware acceptance follows
from this qualification.

## Reproduction

Run `python tests/retained_power/home_low_battery.py --watch /path/to/pinned-watch
--system /path/to/pinned-system --utilities /path/to/pinned-utilities --assets
/path/to/verified-release-inputs --output /path/to/evidence`.

The dedicated workflow checks out the exact PR head and records its identity.
The inherited PR #84 workflow remains unchanged and independently reruns its
previous fixtures. Actions transport artifacts expire after 30 days; the receipt
and terminal CI identity under this directory are the permanent record.

## Verified GitHub checkpoint

[Exact-head CI 39743754996](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/actions/runs/39743754996)
completed successfully at source head
`893f69f671f12a7c8a2f7c9db3a37a3d040dc99d`, job `119707039316`.
All 20 scenario executions and 50 Home invocations passed. The generated
[full receipt](evidence/893f69f/home-low-battery.json),
[CI identity](evidence/893f69f/ci-identity.json),
[all new composition text logs](evidence/893f69f/logs.json), and
[hash manifest](evidence/893f69f/manifest.json) are preserved here independently
of Actions retention. This is new PR #87 evidence only; it contains no prior
PR #84 evidence archive or unrelated payload.

The downloaded 14,678-byte Actions transport ZIP had SHA-256
`d5988667c98a539c9828c4a9003b3b09e1361ce4debde39e31dc6bb20833a9b9`.
It was rehashed, safely extracted, and every command log and both fixture source
hashes were verified against the receipt before these text records were saved.
The complete receipt SHA-256 is
`8718bde2d097175f71305b46e3829c96d2d060e1cf729f4fd678c89e5977cc79`.
The receipt identifies the compiler, all 28 definitions, source pins, six rejection
controls, all commands, return codes, log hashes, and per-scenario results.
