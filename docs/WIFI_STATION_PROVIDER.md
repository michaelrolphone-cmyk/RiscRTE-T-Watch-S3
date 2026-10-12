# Shared Wi-Fi provider 0.3.0

Extends the existing deployed asynchronous provider0.2.1 at
a304597bf26491483bb0a567569f0ca0267cdf9c, used by X4 as well as Watch.
The net.wifi@1 and async prefixes remain unchanged. A complete optional outer
station-management table is advertised only when the platform provides the
matching size/tag/version and all callbacks. It forwards copied configuration,
observations and connected scan/probe requests through the existing radio claim,
operation IDs and service leases. No rendering or direct ESP SDK code is added.

Headers RiscWifiStationV1/GardenWifiStationV1 are copies of the Runtime contract;
RiscWifiManagerV1 is copied from System Apps. Tests verify identical bytes across
the selected component sources. It needs the matching native extension for the
new Manager; old async clients continue to use their original prefix.

`python scripts/build_wifi_station.py --output build/wifi` builds just this
provider. TWATCH_CC selects the pinned Xtensa compiler. Normal/sanitized production
provider+CpuPort+worker integration runs in the companion Runtime repository.
Physical X4/Watch/network testing has not been performed. No firmware flash or
change to unrelated watch components is implied by this provider source update.
