# T051 Wi-Fi / shared keyboard — T-Watch 1.1.28

Shared System source 12352fc46067c32e18f254562d0ec7819f3478ac retains the published T051 scan/join timeout fix and selects the shared text-input client in the full-feature Watch build. The product adds ui.text-input and app.catalog grants for Wi-Fi, preserving all existing grants. Wi-Fi 1.1.30 stores multiple saved networks in internal namespace 6 through the existing native NVS adapter. No SD route is selected on T-Watch.

The exact 1.1.27 image is the input. Only wifi_settings.elf, its manifest, boot.json and cohort.json change. Restored Springboard, Home/Clock, native firmware, all other apps, SDR and geometry remain byte-identical. The full-feature recipe excludes Spectrum-only launch/Home guard flags; strict native admission rejects unresolved application hooks.

Verification: complete Runtime graph and all 59 ELFs admitted; normal/UBSan two-profile write/reentry/separate-process restart/edit/delete/fault tests with the actual native NVS adapter; shared controller workflow and profile tests; atomic and availability tests remain opt-in for other products. No hardware execution claimed. No changed SD files are required for T-Watch.

Rebuild with scripts/build_t051_wifi.py --baseline <published-1.1.27.bin> --wifi <qualified-wifi.elf> --runtime <26a54ff7769f7c9072a2a133790cd293b72abcba> --output <directory>. Target command and ELF normalization/compaction receipts are included. The full image erases device data when flashed at offset 0.
