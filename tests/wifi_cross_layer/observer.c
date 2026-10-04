#include "fixture.h"
#include "RiscRuntimeV1.h"
#include <assert.h>
__attribute__((visibility("default")))void app_main(void){
 const risc_runtime_api_v1*r=risc_runtime_get_api(1);risc_runtime_capability_v1 g={.struct_size=sizeof(g)};
 assert(!r->acquire("net.wifi",1,15,&g)&&!r->acquire("storage.key-value",1,6,&g));
 wifi_test_event("observer-denied-radio-and-credentials");
 assert(r->request_launch("consumer.elf"));
}
