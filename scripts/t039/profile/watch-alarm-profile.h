#include "AlarmServiceV1.h"
#define ALARM_MODE_VISUAL 0u
static inline uint32_t alarm_service_output_modes(const alarm_service_v1*s){return s?ALARM_MODE_BOTH:ALARM_MODE_VISUAL;}
