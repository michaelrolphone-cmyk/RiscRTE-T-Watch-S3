#pragma once
#include "RiscDisplayOutputV1.h"
#ifdef __cplusplus
extern "C" {
#endif
bool watch_boot_render(const risc_display_surface_v1 *, uint32_t milliseconds);
bool watch_ripple_render(const risc_display_surface_v1 *, uint32_t scan);
#ifdef __cplusplus
}
#endif
