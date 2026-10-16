# T054 Watch NVS integration, 1.1.32

The exact 1.1.31 factory image is the baseline (SHA-256 5895c631a9e1181de86ad14a0e7cf95b409de04c30a9d45da12b50d456189b67). Unlike X4/Waveshare, Watch uses the existing synchronous internal NVS implementation. Do not enable the other products' copied atomic service or SD fallback on this product.

Rebuild shared Home with `scripts/build.py --preferences nvs`, its locked System and Utilities sources, and GCC 8.4. The NVS profile shares the canonical sleep/time headers while retaining all existing Home features. Rebuild Settings and Springboard using `scripts/t054/build_apps.py` and the recorded recipes (resolve source paths against the pinned checkouts). These select current native-height UI, ordered touch, tap calibration, and synchronous checked preference saves. All three manifests retain the deployed capability requirements and bump their app versions. The atomic profile remains byte-identical to the published Waveshare artifacts.

Compose with `scripts/t054/assemble.py`; run `scripts/t054/verify.py` with the source-bound native Runtime 26a54ff7769f7c9072a2a133790cd293b72abcba and its exact watch-expanded ELF. The native image, partitions, NVS/app-data, boot registration/grants, every provider, Wi-Fi, BLE Buttons, Files, keyboard, Spectrum, and all other apps remain byte-identical. No Watch SD overlay is required.

Qualification uses Home cold/light/deep wake and RTC reconciliation, synchronous Settings/Quick controller tests, normal/ASan/UBSan, production NVS cold-process persistence, complete 59-ELF Runtime admission, and actual-image preserving-update tests for both banks. The software snapshots and mocked peripheral boundaries do not qualify physical hardware. No device is flashed.
