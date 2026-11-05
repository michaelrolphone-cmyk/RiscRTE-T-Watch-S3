# Isolated Watch local Wi-Fi native qualification

This is a native-dependency qualification candidate, not a product activation.
No released profile, recipe, application, provider, grant, saved data, partition,
firmware version or publication path is changed. No device operation is run.

## Verified inputs and ownership

The base is Watch main 81dbde86969615f7378cc03c5800960a9092e076.
PR89 (2050c9f4c40b4951efdc9a59edd9d2c871c30ed7) owns the independent
native/Home convergence recipe. PR91 (c69d7914935fccdc04749f7bfa429c74219bf88a)
owns its 48-provider capacity derivative and passed native build 41483505761.
Its artifact 13161732109 is evidence for that pin, not this candidate. Neither
owner's files nor branches are changed or copied into this work.

The two qualification builds use exact Runtime
532c502fb2aad358d46166d5fd1df8358148f20e (0.4.23), SDK6.1
fff9895c82d744c7237be8847347bdd1b07c6643 and the existing pinned GCC15/container.
Both start from the complete current native-provisioning profile. The baseline
retains its 40 providers, 32 platforms, 64 installed apps, 32 policy/requirement
rows, IQ, HTTP, TCP, entropy, serial, AppData, native package-volume and preserving
next-boot request selections. Hardware remains owned by the existing providers.

Historical Runtime4107 and the selected Runtime have the identical partition
blob b7f916aa0261e0723fe0f5eb75977a847c67290e. AppData remains at 0x270000
with 0x80000 bytes. Native slots remain 0x260000 bytes and bootfs slots
0x550000 bytes. Qualification compares the actual generated partition binary.

## Explicit policy boundary

The local variant adds the real Backend/Assembly/Worker/Lifecycle/atomic/custody
path. It selects LocalOnly, external volume instance0, namespace-mask2 (Wi-Fi
namespace6 only), and exactly the wifi_settings writer. Namespace1 is not
selected for hydration or interception and retains its ordinary preferences
backend. No external volume is invented and no SD acknowledgment is fabricated.

Checked fresh genesis remains explicitly disabled. A real existing local receipt
may resume; complete legacy namespace6 input may be imported under the native
fence. Empty or conflicting storage does not become a usable fresh baseline.
External-policy roots/receipts must fail closed. The underlying Runtime's source
and host evidence remain separate from this Watch target qualification.

The explicit Watch logical domain is a stable native identity, not a physical
card ID, MAC address, secret or migration permission. Both permanent 8192-byte
workers are retained even though only namespace6 is selected. No resource saving
is inferred from the namespace mask.

## What the workflow checks

The new contents-read workflow runs for a matching PR or explicit manual dispatch.
There is no push trigger, so branch creation plus PR publication does not duplicate
the two native builds.
It never creates a release, updates a feed, packs an app/store, or invokes hardware.
It builds baseline and LocalOnly variants independently from the same exact pins,
without modifying source or accepting an earlier build/cache as attestation.

The existing controlled builder records compiler, Ninja/object/header/link and
source closure. The additive guard rejects any pre-existing path change. Negative
controls reject altered physical/profile selections, policy flags, capacities,
headers and source scope. Actual compiler rows are checked against the expanded
profile; the local header and flags must really reach the compilation.

The linked checks retain SDK6 configuration, rollback/project identity,
INTERNAL controls, IRAM yield, time32, Arduino-free linkage, app capacity and
IQ reservation/ROM proof, slot sizes and ELF/BIN identity. A non-linked target
probe compiles with the actual Runtime row to measure assembly, backend,
worker/TCB, Runtime and CpuPort object sizes. Target compiler frames and static
linked sections are retained. The reported dynamic-control allocation formula
includes alignment overhead and both workers; it is not a free-heap measurement.

The source lock uses Runtime0.4.23 as an evidence label only. It reserves no
product version and its frozen status is not product qualification.

## Required before any released activation

This candidate has not been executed when initially prepared. Passing builds
would establish only the checks above, not final product acceptance.

Still required are live INTERNAL/PSRAM high-water and complete stack-call-chain
admission; real shared AppData allocation/replacement capacity across all writers,
fragmentation and reboot; exact retained provider/application/lifecycle graph and
final byte-identical Wi-Fi app composition; and physical qualification. Existing
Home source-access and other owners' unresolved decisions remain separate.

In particular, no safe persistent-space reserve is guessed, old replicas or
legacy input are not deleted, fresh permission is not enabled, and successful host
or linked software proof is not evidence that an installed device was tested.
