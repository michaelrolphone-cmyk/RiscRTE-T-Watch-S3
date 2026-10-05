#pragma once
#include "PointsRecords.h"
#include "faces/points_state.h"
/* Keep the pure Utilities time converter in its own translation unit; the
 * Watch and shared client expose ABI-identical RTC typedefs under different
 * header paths and must not both declare them inside crown.c. */
bool watch_points_projection(const points_config *,const points_meta *,uint32_t,nova_points_state *);
