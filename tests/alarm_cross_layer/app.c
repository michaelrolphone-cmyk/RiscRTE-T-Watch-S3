#include "fixture.h"
#include "RiscRuntimeV1.h"
#include "apps/clock/watch_alarm_sleep.h"
#include <assert.h>
#include <string.h>
static const alarm_service_v1 *actual;
static int32_t status(void*c,alarm_status_v1*s){(void)c;probe_service("status");return actual->status(actual->context,s);}
static int32_t step(void*c){(void)c;probe_service("step");return actual->step(actual->context);}
static int32_t refresh(void*c){(void)c;probe_service("refresh");return actual->refresh(actual->context);}
static int32_t prep(void*c,alarm_sleep_v1*s){(void)c;probe_service("prepare");int32_t result=actual->prepare_sleep(actual->context,s);if(result==ALARM_OK)assert(s->deadline==probe_expected_deadline());return result;}
static alarm_service_v1 observed;
__attribute__((visibility("default"))) int app_module_init(void){probe_event("app-init");return 0;}
__attribute__((visibility("default"))) void app_module_fini(void){probe_event("app-fini");}
__attribute__((visibility("default"))) void app_main(void){
 (void)watch_sleep_prepared;const risc_runtime_api_v1*rt=risc_runtime_get_api(1);assert(rt);
 risc_runtime_capability_v1 ag={.struct_size=sizeof(ag)},pg={.struct_size=sizeof(pg)};
 assert(rt->acquire("alarm.service",1,0,&ag)&&rt->acquire("test.sleep",1,7,&pg));actual=ag.api;
 const sleep_fixture_v1*p=pg.api;observed=*actual;observed.status=status;observed.step=step;observed.prepare_sleep=prep;observed.refresh=refresh;
 if(!strcmp(probe_mode(),"old-order")){
  assert(p->panel->prepare_sleep(NULL));assert(p->panel->prepare_deep_sleep(NULL)==0);
  alarm_sleep_v1 decision={.struct_size=sizeof(decision)};assert(actual->prepare_sleep(actual->context,&decision)==ALARM_PENDING);
  assert(actual->step(actual->context)==ALARM_STORAGE);
  assert(p->panel->resume(NULL));assert(actual->refresh(actual->context)==ALARM_PENDING);
  assert(actual->step(actual->context)==ALARM_STORAGE);probe_event("permanent-revocation-proved");
 }else{
  unsigned mode=strstr(probe_mode(),"hybrid")?PORTABLE_SLEEP_HYBRID:PORTABLE_SLEEP_DEEP;
  int rc=watch_alarm_sleep_prepared(p->panel,p->pmu,mode,&observed,rt->diagnostic);probe_result(rc);
  if(rc==WATCH_SLEEP_RETAINED){probe_event("app-retained-return");return;}
  alarm_sleep_v1 decision={.struct_size=sizeof(decision)};
  assert(watch_alarm_deadline(&observed,&decision)==ALARM_OK);probe_event("post-restore-kv-live");
 }
 assert(rt->release(&ag)&&rt->release(&pg));probe_event("app-normal-return");
}
