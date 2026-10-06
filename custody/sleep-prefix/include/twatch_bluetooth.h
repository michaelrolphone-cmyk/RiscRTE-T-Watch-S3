#pragma once
/* Watch's append-only bluetooth.hci@1 control extension. Packet prefix remains
 * unchanged; callers must require the complete struct_size before controls. */
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
enum { PORTABLE_BLUETOOTH_OFF=0, PORTABLE_BLUETOOTH_ON=1, PORTABLE_BLUETOOTH_RETAINED=2 };
typedef struct {
 uint32_t api_version,struct_size;void *context;
 bool (*send)(void*,uint8_t,const uint8_t*,size_t);
 int32_t (*next)(void*,uint8_t*,uint8_t*,size_t,size_t*);
 bool (*set_enabled)(void*,bool);
 bool (*status)(void*,uint8_t*);
} portable_bluetooth_control_v1;
