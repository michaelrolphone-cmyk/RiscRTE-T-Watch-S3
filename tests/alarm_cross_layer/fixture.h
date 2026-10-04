#pragma once
#include "twatch_power.h"
#include "twatch_caps.h"
typedef struct { uint32_t api_version,struct_size; const twatch_panel_power_v1 *panel; const twatch_pmu_api_v1 *pmu; } sleep_fixture_v1;
#ifdef __cplusplus
extern "C" {
#endif
const char *probe_mode(void);
void probe_event(const char *);
void probe_delay(unsigned);
void probe_service(const char *);
void probe_result(int);
uint32_t probe_expected_deadline(void);
bool probe_rtc(twatch_rtc_time_v1 *);
#ifdef __cplusplus
}
#endif
