#include "fixture.h"
#include "WifiApi.h"
#include "RiscRuntimeV1.h"
#include "RiscKeyValueV1.h"
#include "PortableWifiCredentials.h"
#include "AlarmServiceV1.h"
#include <assert.h>
#include <string.h>
static void alarm_check(const alarm_service_v1*a,bool healthy){
 (void)a->refresh(a->context);
 for(unsigned i=0;i<64;i++)(void)a->step(a->context);
 alarm_status_v1 status={.struct_size=sizeof(status)};
 assert(a->status(a->context,&status)==ALARM_OK);
 if(healthy)assert(status.state==ALARM_STATE_READY&&status.error==ALARM_OK);
 else assert(status.state==ALARM_STATE_BLOCKED&&status.error==ALARM_STORAGE);
}
__attribute__((visibility("default")))int app_module_init(void){wifi_test_event("init");return 0;}
__attribute__((visibility("default")))void app_module_fini(void){wifi_test_event("fini");}
__attribute__((visibility("default")))void app_main(void){
 const risc_runtime_api_v1*r=risc_runtime_get_api(1);assert(r);
 if(wifi_test_invocation()>1)return;
 risc_runtime_capability_v1 ng={.struct_size=sizeof(ng)},sg={.struct_size=sizeof(sg)},kg={.struct_size=sizeof(kg)},ag={.struct_size=sizeof(ag)};
 assert(r->acquire("net.wifi",1,15,&ng)&&r->acquire("test.sleep",1,7,&sg)&&r->acquire("storage.key-value",1,6,&kg));
 assert(r->acquire("alarm.service",1,0,&ag));const alarm_service_v1*alarm=ag.api;
 const wifi_api_v1*w=ng.api;const test_sleep_v1*s=sg.api;const risc_key_value_v1*k=kg.api;
 assert(w->struct_size>=WIFI_MANAGEMENT_V1_SIZE);
 uint8_t record[64]={0};uint32_t n=0;assert(k->get(k->context,"w_cfg",record,sizeof(record),&n)==RISC_KEY_VALUE_NOT_FOUND);
 portable_wifi_credentials profile={.ssid="FixtureOnly",.password="fixture-password"};
 assert(portable_wifi_credentials_save(k,&profile)==PORTABLE_WIFI_CREDENTIALS_SAVED);
 portable_wifi_credentials_clear(&profile);
 assert(s->light()==0); /* Boot-owned idle radio claim must not block sleep. */
 assert(w->scan_start(w->context));alarm_check(alarm,true);assert(!w->connect(w->context,"FixtureOnly","fixture-password"));
 assert(s->light()==RISC_LIGHT_SLEEP_BUSY&&!r->request_launch("observer.elf"));
 garden_radio_scan_result_v1 scan={.struct_size=sizeof(scan)};assert(w->scan_poll(w->context,&scan)&&scan.state==GARDEN_RADIO_SCAN_DONE&&scan.count==1);
 assert(w->scan_cancel(w->context));
 if(!strcmp(wifi_test_mode(),"join-retry")){assert(!w->connect(w->context,"FixtureOnly","fixture-password"));wifi_test_recover();}
 assert(w->connect(w->context,"FixtureOnly","fixture-password"));
 assert(w->status(w->context)==WIFI_LINK_UP&&w->rssi(w->context)==-43);alarm_check(alarm,true);
 assert(s->light()==RISC_LIGHT_SLEEP_BUSY&&!r->request_launch("observer.elf"));
 if(!strcmp(wifi_test_mode(),"live-return")){wifi_test_event("retained-return");return;}
 if(!strcmp(wifi_test_mode(),"cleanup-retained")||!strcmp(wifi_test_mode(),"cleanup-retry")){
  assert(!w->disconnect_checked(w->context));
  assert(s->light()==RISC_LIGHT_SLEEP_RETAINED&&!r->request_launch("observer.elf"));
  if(!strcmp(wifi_test_mode(),"cleanup-retained")){alarm_check(alarm,false);wifi_test_event("retained-return");return;}
  wifi_test_recover();
 }
 assert(w->disconnect_checked(w->context)&&w->status(w->context)==WIFI_LINK_DOWN);
 alarm_check(alarm,true);assert(s->light()==0);
 assert(r->release(&ng)&&r->release(&sg)&&r->release(&kg)&&r->release(&ag));
 assert(r->request_launch("observer.elf"));wifi_test_event("queued-after-cleanup");
}
