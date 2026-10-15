# T-Watch 1.1.36 app and SDR repair

Successor to the exact official 1.1.35 prerelease; 1.1.34 remains reserved for provisioning. The complete 121-file, 59-ELF baseline is locked by per-file hashes and its 16 MiB factory hash.

Runtime 4107eaeedd8c801eeaf7deb1c7bc4a943cd27342 is a descendant of 54461e8a7f61b28600b8ec8dcaf27b12cd45e829 and preserves selectable trace capacity. The product retains the existing watch-native-ui profile, 64 trace records, 32 policy/requirement rows, ABI3 store geometry, IQ reservation and all hardware driver composition.

Seventeen inherited apps receive bounded shared adapter repairs with per-app source and recipe custody. Their manifests may change version only. Springboard ELF and manifest remain byte-identical to official 1.1.35, whose System source is f31f89636304d202c49884e2e9b2e0b2ec5fb891. This release intentionally has per-artifact source pins rather than falsely assigning all ELFs to one System revision.

Final app manifest and source-reproduction gates are pending. Asset publication stays disabled until qualification passes. No provisioning merge, hardware access or flash is part of this composition. Non-Plus T-Watch-S3 with BMA423; the physical radio variant and antenna band require confirmation.
