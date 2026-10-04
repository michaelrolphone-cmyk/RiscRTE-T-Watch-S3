/* Independent later network-app analogue, with separately granted authority.
 * The format is shared with Settings; no copied private app logic. */
#include "fixture.h"
#include "RiscRuntimeV1.h"
#include "PortableWifiSavedNetwork.h"
#include <assert.h>
#include <string.h>
__attribute__((visibility("default")))void app_main(void){
 const risc_runtime_api_v1*r=risc_runtime_get_api(1);
 risc_runtime_capability_v1 ng={.struct_size=sizeof(ng)},kg={.struct_size=sizeof(kg)};
 assert(r->acquire("net.wifi",1,15,&ng)&&r->acquire("storage.key-value",1,6,&kg));
 const wifi_api_v1*w=ng.api;const risc_key_value_v1*k=kg.api;
 assert(portable_wifi_saved_network_connect(k,w)==PORTABLE_WIFI_SAVED_NETWORK_STARTED);
 assert(w->status(w->context)==WIFI_LINK_UP);
 assert(w->disconnect_checked(w->context));
 assert(r->release(&ng)&&r->release(&kg));
 wifi_test_event("consumer-reused-saved-profile");
}
