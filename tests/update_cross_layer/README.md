# Source-wired update integration evidence

This host-only harness combines the actual update service with the real Runtime,
provider graph/module loader, CPU port, native HTTP parser/transport state machine,
and paired-bank/store-admission code. It does not replace the bank or HTTP API
with happy-path mocks.

## Run

From any directory:

```sh
bash tests/update_cross_layer/run.sh /path/to/runtime /path/to/system-apps /path/to/bootloader.bin
SANITIZE=1 BUILD_DIR=/absolute/writable/build-dir bash tests/update_cross_layer/run.sh /path/to/runtime /path/to/system-apps /path/to/bootloader.bin
APP_DATA_TEST=1 BUILD_DIR=/absolute/writable/abi2-dir bash tests/update_cross_layer/run.sh /path/to/current-runtime /path/to/current-system-apps /path/to/bootloader.bin
```

The third argument must identify the verified 15,104-byte rollback bootloader. Its SHA-256 is checked by production `knownBootloader()`. Builds and
fixtures stay beneath `BUILD_DIR`, defaulting to this directory's `build`.
`JOBS=4` runs up to four independent host cases in parallel (target builds are
not performed). Completed power snapshots are retained as `power-flash.bin.gz`.
The script does not use networking, device access, credentials, production
partitions, release indexes, publication, or deployment.

`APP_DATA_TEST=1` selects the existing ABI2 constants (0x260000 native slots,
0x510000 stores) and the separate 0x270000/0x80000 app-data partition. NVS and
app-data contain non-erased sentinels. Every native write/erase must target only
the inactive pair or its journal sector; all scenarios and saved power-cut
snapshots preserve NVS and app-data bytes. The normal ABI1 lane retains its
original geometry. These checks exercise the native bank write set; physical
SPIFFS/LittleFS behavior and unrelated application preference writes are not
substituted for device qualification.

## Executed production chain

1. A tiny host probe app is loaded through Runtime's `esp_dlopen_instance` adapter.
   It gets the real `risc_runtime_get_api(1)` interface. Lifecycle hooks and app
   grant policy are real.
2. Runtime validates board/boot manifests and starts both production update
   providers through `GraphV2` / `ModuleV2`. The service source is compiled into
   separate real shared ELF modules for firmware and apps. The app can acquire
   only its authorized action kind.
3. Provider dependencies are resolved by the actual graph to CPU-port HTTP/clock
   tables and `NativeBankStore`'s table. No raw bank or HTTP grant is given to the
   probe app.
4. Refresh reads a controlled HTTP response through production `NativeHttp` and
   the pinned SDK `http_parser.c`, then the unmodified product catalog parser and
   service classify, prepare, download, finish, verify, activate and restart.
5. Production `PairedBank` copies and hashes actual full-size fake flash regions,
   invalidates the inactive journal before mutation, verifies final payloads,
   writes readiness, and selects the boot bank last. Production native app
   admission executes `Runtime::appUpdate`, ELF structural validation, ordinary
   import whitelist plus symbol availability, full readback hash, and `StoreAudit`.
6. Fresh processes restore flash snapshots and use actual `prepareBoot` plus
   explicit default-entry health confirmation. Selected firmware is checked by
   a separately compiled host Runtime identifying itself as 0.1.12. The original
   0.1.11 host Runtime is also required to reject that newer selected image.

## Coverage

Both action kinds exercise:

- Their own service grant; rejection of the other service and raw HTTP/bank
- Malicious boot policies requesting raw HTTP or bank access, rejected before
  any module load, HTTP open, flash write or health confirmation
- Explicit independent KV namespace 1 and 6 grants, ambiguous instance 0 denial,
  namespace 5 denial, copied-context revocation, and missing-6 denial
- No update transaction before explicit default-entry health confirmation
- Native authority rejection for unknown identities, changed/escaping/absolute
  paths, extra grants, changed/removed requirements, wrong entry, non-new or
  malformed versions; these are additional privileged harness calls to the real
  native boundary, not APIs exported to the probe app
- Success, cancel, cancel then retry, network failure, network failure then retry,
  timeout, short response, corrupted payload, and closed transport before READY
- Inactive-bank-only mutations and exact active firmware/store/journal retention
- Refusal to activate before READY and refusal to cancel after selection
- Owner-checked restart, activation uncertainty, and lifecycle retention
- Power cuts while copying, downloading, READY before selection, and after
  selection, followed by fresh-process boot-pair validation and confirmation

App-specific checks include valid synthetic Xtensa ELF admission, corrupt ELF,
forbidden privileged import, unavailable otherwise-allowed import, unauthorized
requirements, post-copy unrelated-file tampering, and unmount-retain/cancel retry.
Successful app update changes exactly the authorized clock ELF/manifest while
preserving every other byte/file in the active and staged store; firmware is
copied unchanged.

Firmware-specific checks include advertised merged image being USB-only without
explicit OTA metadata, rejection of old actual Runtime version despite newer
catalog metadata, incompatible actual store-ABI marker, and bit-identical current
store preservation.

## Important boundaries

- The probe is a host test client, not the product display/touch/radio UI. The
  existing portable controller/adapter tests cover that UI; this harness tests
  the backend and lifecycle seam they consume.
- TLS socket operations are synthetic. Real transport framing, bounded buffers,
  timeout state, configuration and cleanup run, but no TLS handshake or real
  certificate chain is performed.
- Fake flash preserves the production 16 MiB addresses and exact bank lengths.
  Fake SPIFFS uses a bounded deterministic file archive materialized into local
  directories. It is not the real SPIFFS implementation or a physical flash/GC
  crash-consistency test. File changes become archive bytes on modeled unmount.
- ESP native image verification and app-description calls are lowest-hardware
  shims. Runtime image payloads contain controlled real markers and hashes but
  are not executable firmware. Synthetic Xtensa app payloads are structurally
  validated but never executed. Host service/probe modules are actually dlopened.
- The compiled native linker-symbol availability call is adapted only for the
  synthetic ELF's `memcpy` import, returning its real host function address or
  zero in the unavailable-import test. The production whitelist still gates it.
- A false return from the synthetic restart occurs after recording a restart
  request; actual device restart does not return.
- Successful ACTIVATED allows app finalization, then the graph retains the
  activated service when it cannot quiesce. ACTIVATION_UNKNOWN and poisoned HTTP
  retain before app finalization. These are separately asserted.
- Sanitizer leak detection is disabled because deliberate retained mappings and
  abrupt process-power cuts must outlive the test invocation. Address and
  undefined-behavior instrumentation remain enabled and nonrecovering.

## Deliverables

- `integration.cpp`: cross-layer assertions and bounded lowest-hardware fixtures
- `probe_app.c`: host Runtime-loaded probe/lifecycle hooks
- `run.sh`: reproducible ordinary and sanitizer build/run matrix
- `shim/`: incremental SHA-256 hardware shim and controlled build identity
CI retains normal/sanitized logs and compressed power-cut snapshots as exact-head evidence.

No production source is edited by this harness. Required production fixes found
elsewhere must be rerun through it before reusing the logs as final evidence.
