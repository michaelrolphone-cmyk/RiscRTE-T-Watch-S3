# Watch 1.0.5 packaging and one-stage upgrade proof

These helpers are separate from the frozen SDR 1.0.3/1.0.4 builders. They prepare
an offline candidate and prove its admission using the installed Runtime source;
they do not publish releases or catalogs, alter source pins, or operate a device.

The only accepted source is hosted Watch 1.0.4 at
`674729dbade10c15368731745844e6dc2f6ebd0b`. Its exact full-image, cohort, native
firmware, and native ELF digests are checked. The extracted source store,
SPIFFS image, release record, and paired journal must agree byte for byte.
Runtime remains `0a4f3d18c5d830d32678092fa99284810334b485`, version 0.1.34.

## Prepare the candidate

Wait for the integrated Watch source to be committed and clean, with
`apps/current-cohort.json` set to 1.0.5 and the complete current-app artifact built
from that exact commit. `current_apps_overlay.verify` from that source checkout
validates its source configuration, hashes, original ELF records, and archive.
The new helper then adds independent bounded authority checks and compiles the
installed Runtime's production graph/ELF validator before packaging.

```sh
python scripts/build_next_watch_cohort.py \
  --source-root /path/to/committed-watch-1.0.5 \
  --previous-bundle /path/to/accepted-674729db/bundle/sdr-upgrade \
  --apps-dir /path/to/current-apps \
  --runtime /path/to/watch-sdr-runtime \
  --native-dir /path/to/accepted-674729db/native \
  --output /new/path/next-watch-cohort
```

The output contains `twatch-s3-cohort-1.0.5.bin`, `bootfs.bin`, the exact store,
`next-watch-build-proof.json`, `LICENSES.zip`, and installation notes. The OTA payload is exactly
native firmware followed by the ABI2 bootfs. No NVS, app-data, bootloader,
partition table, journal, or initial full image is emitted as an upgrade.

Full initial images are destructive provisioning inputs. Never use one to
upgrade an installed/data-bearing Watch, write the empty app-data image, or
serial-flash the cohort at offset zero. This is one paired-cohort transaction
from accepted 1.0.4; it needs no native bridge stage.

## Prove the exact bytes

The Python environment needs the existing release tooling dependencies, including
`pyelftools`; the host needs C/C++ compilers and OpenSSL development libraries.
Run against a new output directory:

```sh
ASAN_OPTIONS=detect_leaks=0 SANITIZE=1 python scripts/test_next_watch_upgrade.py \
  --previous-bundle /path/to/accepted-674729db/bundle/sdr-upgrade \
  --native-dir /path/to/accepted-674729db/native \
  --runtime /path/to/watch-sdr-runtime \
  --candidate-bundle /path/to/next-watch-cohort \
  --output /new/path/next-watch-upgrade-proof
```

The proof runs the actual installed `Runtime::validateCohort`, actual provider
binding and app manifest validation, production ELF admission using the exact
native ELF's public exports, and target self-admission. It rejects wrong or
missing migration origins/targets/entries, attempts to acquire existing private
KV/app-data namespaces, provider namespace theft, reassigned prior owners,
changed hardware, unexpected files, and corrupt application ELFs.

The transaction test includes Runtime's existing `native_bank_test.cpp` boundary
and compiles the real `PairedBank.cpp` and native flash adapter. The staged-store
callback binds the independently executed production admission result to the
exact store bytes written by the transaction. It does not substitute a simulated
state machine or grant policy.

Each interruption writes a full flash snapshot and starts a fresh process to
model loss of in-memory transaction state. Tests cover begin, partial native and
store download, cancellation, corrupt native/store payloads, native/store
verification, ready state, unknown activation, candidate rejection/rollback,
selection, success, and retry from each interrupted/rejected snapshot. Every
snapshot compares all original NVS and app-data bytes, the original native/store
pair, and its journal. Nonuniform persisted sentinels detect accidental blanking,
shifts, and partial changes. Retry must install the exact native/store candidate.
A candidate boot uses the real native boot checks; rejection calls the real native
rollback hook. The IDF selection/rollback and flash boundary remains the existing
host fixture.

`next-watch-upgrade-proof.json` identifies every result, input digest, rejection,
and snapshot digest. Consumed snapshots are discarded after their reboot/retry
checks to keep disk use bounded. It explicitly records that target instructions, physical flash,
SPIFFS mounting, TLS, hardware power loss, and device health confirmation were not
executed. These host proofs do not qualify a device or replace physical tests.

Before the 1.0.5 artifact exists, use the same command with `--check-installed`
instead of `--candidate-bundle`. It checks accepted-source custody, self-admission,
and all transaction/reboot/retry paths using the unchanged real 1.0.4 cohort. Its
scope is explicitly `accepted-1.0.4-harness-self-test-only`; it cannot establish
1.0.5 integration acceptance.

## Bounded authority

Every prior application grant row, prior provider binding/key row, identity, and
manifest authority is retained. Versions, descriptions, and executable bytes
may change through the verified current-app build. All prior owners are recorded
in the proof; no list of selected examples substitutes for comparing every owner.
The hardware board bytes are unchanged.

Only `ble_touchpad`, `ble_buttons`, and the logical `ble-hid` provider are added.
HID is Global0 without a hardware instance. It consumes the unique existing
`bluetooth.hci`, `platform.clock`, and bound namespace 10 with exactly `hid_ours`,
`hid_peer`, `hid_ccc`, and `hid_identity` read/write keys. Only BLE Buttons gets
private namespace 11. Both apps receive shared namespace 1 through exactly two
Runtime generic migration entries from accepted 1.0.4/source 674729db to 1.0.5.
The previous Waterfall migration is replaced, never broadened or replayed.

Run the focused policy regression tests with:

```sh
python -m unittest discover -s tests -p test_next_watch_cohort.py -v
```
