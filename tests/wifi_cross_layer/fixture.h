#pragma once
#include <stdint.h>
#include "RiscLightSleepV1.h"
typedef struct { uint32_t api_version,struct_size; int32_t(*light)(void); } test_sleep_v1;
#ifdef __cplusplus
extern "C" {
#endif
const char*wifi_test_mode(void);
void wifi_test_event(const char*);
unsigned wifi_test_invocation(void);
void wifi_test_recover(void);
#ifdef __cplusplus
}
#endif
