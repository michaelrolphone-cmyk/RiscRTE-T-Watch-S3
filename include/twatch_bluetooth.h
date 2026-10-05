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

/* Exclusive host lease, append-only. Unleased controls/packets reject while a
 * host owns it. claim may fail with a nonzero token: release is still required.
 * release closes/reset the controller to prove scanning is over, then restores
 * prior enabled state. 1 restored; 0 safe OFF (restore failed); -1 retained.
 * Token is valid until a nonnegative release. No callback survives release. */
typedef struct {
 portable_bluetooth_control_v1 controls;
 bool (*claim)(void*,uint64_t*);
 bool (*send_owned)(void*,uint64_t,uint8_t,const uint8_t*,size_t);
 int32_t (*next_owned)(void*,uint64_t,uint8_t*,uint8_t*,size_t,size_t*);
 int32_t (*release)(void*,uint64_t);
} portable_bluetooth_host_v1;
