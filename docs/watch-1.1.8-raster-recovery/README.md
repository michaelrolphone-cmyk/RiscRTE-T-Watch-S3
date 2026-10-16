# Watch 1.1.8 Springboard recovery test

This test increment repairs the severe Springboard dragging regression reported on 1.1.7. The user confirmed that 1.1.6 icon scrolling remains usable.

The Watch display is cooperative: status queries do not transmit rows. The repair yields at bounded intervals during private raster work so accepted output can progress, while preserving immutable provider-owned buffers, latest complete frames, input state and fail-closed retention. Checked monotonic timestamps avoid thousands of expensive health samples during a rendered frame. Optional clock absence retains the legacy fallback.

Focused host tests use the actual Springboard renderer and exact Watch display implementation with explicitly modeled raster CPU cost. They establish the previously missed starvation path and software contracts; they do not establish physical FPS or hardware qualification. The compact adapter ancestry is intentional and is not a port of modern X4 keyboard/UI features.

All 25 apps, 30 providers, crown/five-second recovery, direct offline sharing, and Contexts 0.4.2/service 0.3.2 remain included. Nineteen generic apps advance one patch version; Files, the Contexts scene, and other components retain their previous exact source/versions. Native Runtime remains the exact compiled 3b90 image.

KNOWN ISSUE: Files crashes on hardware in both 1.1.6 and 1.1.7. Its separate Runtime-table bounds repair is blocked and is NOT in this image. Avoid opening Files while testing scrolling. Sharing code is retained but the Files entry point remains unusable until its repair is qualified.

This Watch has no SD card dependency. This is a full initial flash image and erases internal settings, saved Wi-Fi credentials and application data. A data-preserving update is not qualified. Final complete-image admission and source receipts accompany the package.
