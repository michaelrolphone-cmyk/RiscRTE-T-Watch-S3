# Wi-Fi Settings development integration

Wi-Fi Settings is an ordinary shared System Apps ELF. It uses the existing
Watch `net.wifi@1` provider, backed by the generic Runtime `platform.radio@1`
station transport. No firmware UI or board-specific network policy is added.

The explicit eleven-app store extends the delivered Points in Time candidate.
All original applications, 32 Clock faces, alarm service and hybrid Light/Deep
sleep remain present. Only integrated Wi-Fi device15 is added; LoRa, Bluetooth,
IMU and AP controls remain outside this deployment. This branch does not alter
or promote the accepted Watch1.0 product release.

## Authority and lifecycle

Only Wi-Fi Settings receives `net.wifi@1` instance15 and credential namespace6.
The five-key saved-profile format is the reusable shared
`PortableWifiCredentials.h` contract. It stores one profile, SSID1–32 bytes and
an empty/open or8–63 printable-character password. Credentials are not embedded
in packages, logs, source pins or generated images. This task uses synthetic
fixture data only and does not connect, configure or flash a real device.

Native radio claim is an exclusive logical reservation. RF initialization is
lazy on an explicit join or scan. A scan produces at most16 copied results;
accepting join is distinct from getting an IPv4 connection. Cancel/disconnect
must complete before a fresh operation or application handoff. Cleanup failure
retains ownership and blocks unsafe sleep/unloading. Ordinary idle radio claims
permit the existing Light/Deep path. Releasing and reacquiring an app grant does
not create a new stack or bypass native ownership.

The shared saved-profile client is intended for later explicitly authorized
OTA/App Store consumers. Such an application can receive the same namespace6
and radio15 grants, validate/load the saved profile and acquire its own bounded
session without re-entering credentials. No grants are assigned to unfinished
apps here. The current Settings session stops RF before leaving or sleeping;
this is this candidate's battery-safe lifetime, not a blanket product rule that
future consumers can never reconnect or share a managed network session.

## Persistence and privacy

Save is explicit. Two two-chunk slots hold64-byte values; the separate selector
is the sole authority and is replaced only after readback validates a complete
inactive slot. Partial/orphan writes never become a fallback profile. Uncertain
writes require readback/recovery or explicit retry. Forget confirms a tombstone
before overwriting both slots. A corrupt/missing selector never resurrects an
old slot. CRCs detect accidents; they are not authentication or encryption.

The current key-value backend does not promise encryption or a secret vault.
Logical overwrite/Forget cannot guarantee physical flash erasure. Users should
review this before saving a password. Volatile credential copies are explicitly
cleared. Full-image flashing replaces lower8MiB/NVS and resets the profile along
with Settings, Stopwatch, alarm/countdown and Points records.

## Software qualification

The driver has normal and ASan/UBSan bounds, legacy-prefix compatibility,
scan-copy and cleanup/retry fixtures. The actual shared Wi-Fi application/adapter, real Runtime/CpuPort, independently
mapped Watch provider and real Points alarm-service ELF are exercised with synthetic RF hardware for grant
isolation, lazy ownership, connection/scan states, sleep gating and retained
failure. Shared app tests exercise the actual adapter/controller, text entry,
Save/Forget, nested Back, alarm interruptions and resumed/retained sleep.

Pinned target ELF ABI/import/export/relocator checks and exact-head hosted CI
are required before candidate delivery. All eight explicit board variants must
reconstruct the same44-file store except board revision, and the actual SPIFFS
pack/unpack must match every file. Physical RF/authentication interoperability,
DHCP timing, power-loss durability, wake reliability and current draw require a
separately authorized hardware session; software fixtures do not establish them.
