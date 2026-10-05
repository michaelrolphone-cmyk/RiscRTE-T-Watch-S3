# Points app → Runtime/service → stored Clock regression

Run the source-wired application/save regression against an actual production
Points store or common/deployment archive:

```sh
SANITIZE=1 ASAN_OPTIONS=detect_leaks=0 python3 scripts/test_points_store_faces.py \
  --runtime ../runtime --system-apps ../system-apps --utilities ../utilities \
  --legacy-utilities ../utilities-legacy --productivity ../productivity \
  --archive dist/points-common/twatch-points-launcher-0.8.0-points-launcher-common.zip \
  --output /tmp/points-store-runtime
```

`--store` accepts an already extracted, complete production store instead.
Legacy Utilities is the original packaged Clock dependency at
`5418d9dc7f9963d96b5b8b11c40658ee753d9cbd`; current Utilities must support custom
Points records. The test builds native modules behind the production target ELF
registry, real Runtime/CpuPort, actual selected drivers, and the actual Points
service. No boot/board/app/provider policy JSON is rewritten. Store inputs are
hashed before and after. Executable replacement occurs in a separate host copy.

The adapter first lets Runtime dispatch from default Clock to the Points app.
It includes the actual app source and invokes its real dependency acquisition,
load_catalog and save_action functions, so saves go through its admitted
namespace-5 grant. It also explicitly changes the time preference through the
real namespace-1 grant. The real service must reconcile successfully through its
bound provider storage. Runtime then unloads Points and reloads the actual Clock;
its real read/decode/projection/render path is observed before module teardown.

The 386 checks cover both matched and historical Clock decoders:

- Factory-fresh defaults with no saved settings or Points records and zero writes
- Empty schedules on selected faces and older basic PTC1 records
- End-only, warning-only, and both end/warning flags
- Both custom kinds (6/7), distinct names and colors, and start/end projection
- Corrupt checksums and backing read errors, with no namespace-5 repair writes
- Latest 12/24-hour preference after leaving Points
- All 33 persisted face IDs with basic records; every schedule face (24–32)
  with every data state
- Module unload counts, resource quiescence, no RTC writes or RF activity

For malformed/read-error cases the hardware model provides a crown-release event
so the actual alarm-service error modal can be dismissed, then checks Clock's
error state. Valid current records must render READY. Historical Clock must
reproduce ERROR only for records outside its decoder's supported schema. The
same real current app and service remain in use on both sides of that test.

`points-results.json` contains each outcome and actual diagnostics.
`provenance.json` records original store custody, JSON hashes, Runtime/Watch/
Utilities/System source state, native registry provenance and sanitizer status.
`points-provenance.json` adds app/legacy source state and test-adapter hashes.

Limits: native host execution, not Xtensa execution or device qualification.
The app's event/render loop and physical input are outside this fixture; its
production dependency/load/save functions are exercised directly. The separate
GUI tests cover interaction dispatch. This fixture reloads default Clock rather
than navigating the launcher-return Clock entry. Historical PTO1 occurrence
ledger migration has separate codec coverage, not this scenario matrix.
