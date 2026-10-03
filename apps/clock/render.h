#pragma once
#include "RiscDisplayOutputV1.h"
#include "twatch_calendar.h"
/* Draws only into the caller's validated RGB565 frame. No allocation or I/O. */
bool watch_clock_render(risc_display_surface_v1 *surface, const twatch_rtc_time_v1 *time,
                        bool valid_time, uint32_t uptime_seconds);
