# Production store admission repair

The Points in Time development BIN from Watch `84f30702` and the Wi-Fi Settings
development BIN from Watch `c3a43464` must not be used. Their stores cannot pass
the Runtime boot admission check. Clock remains version 0.7.0 and Wi-Fi Settings
remains version 1.1.0; this repair changes their paired Runtime and verification.

## Failure and scope

The default Clock, return Clock and Points in Time policies explicitly grant
`storage.key-value@1` namespaces 1 and 5. Each manifest declares that capability
once. Runtime 0.1.8 (`8688f920`) and 0.1.9 (`e972f0ff`) require exactly one matching
grant per capability, so both delivered stores fail `Runtime::prepare` with
`app requirement not uniquely authorized`. Admission validates all policies
before any module runs, so the complete image is blocked, including Wi-Fi
Settings even though its own storage policy has only namespace 6.

The prior artifact checks correctly reconstructed the profile archives, ELF
payloads and SPIFFS contents. They did not run those policies through Runtime
admission. The Points lifecycle test generated a separate policy containing
only `test.sleep` and `alarm.service`. The Wi-Fi lifecycle test used a generated
default-app policy with namespace 6. These tests exercised their stated paths,
but did not establish that the delivered default Clock could boot. Statements
that the complete delivered candidates were ready were therefore incorrect.

The separate Runtime 0.1.10 repair permits distinct explicitly selected storage
namespaces under one capability declaration, retaining the eight-grant bound.
Duplicate namespace grants, undeclared grants and ambiguous instance-zero
acquisition remain errors. Other capability selection rules are unchanged.
There is no OTA, App Store, application feature or partition-layout change here.

## Required gates

`scripts/check_runtime_store_admission.py` compiles the paired production
Runtime and CpuPort. It extracts actual deployment archives, SPIFFS images or
the bootfs partition from a complete BIN, writes their bytes unchanged into a
temporary store, and calls `Runtime::prepare`. Native hardware and storage
callbacks are counted and must remain unused. It verifies the store is still
byte-identical afterward. A successful admission check does not execute Xtensa
instructions or qualify hardware.

CI checks all eight Points and all eight Wi-Fi profile stores and both common
SPIFFS images. The old Runtime must reject the same untouched inputs with the
known diagnostic; the repaired Runtime must admit them. The production-store
execution test separately compiles current Clock and selected production
providers for the host, keeps all board/manifests/policies unchanged, and checks
actual default-app capability acquisition, frame output and cleanup using a
model only at the native peripheral boundary.

Final BIN assembly reruns admission on all eight source profiles, the common
store, unpacked hosted SPIFFS and bytes extracted from the assembled final BIN
before writing a deliverable. `apps/wifi-store-baseline.json` fixes every one of
the 44 previously delivered store file hashes. All 44 must remain byte-identical
in this Runtime-only replacement. Source identity metadata outside the store
may change to identify the repair.

Hardware RF, authentication, DHCP, sleep/current, physical storage durability
and other device behavior still require user-controlled testing. No hardware
flashing or network configuration is part of these gates.
