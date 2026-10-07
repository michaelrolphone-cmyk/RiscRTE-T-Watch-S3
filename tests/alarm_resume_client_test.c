/* Current-only suffix contract; the included legacy cases remain separately
 * compiled without WATCH_ALARM_SLEEP_RESUME. */
#define WATCH_ALARM_SLEEP_RESUME 1
#define main legacy_alarm_sleep_test_main
#include "alarm_sleep_test.c"
#undef main
static alarm_service_sleep_v1 extended;
static alarm_sleep_v1 issued;
static unsigned resumes;
static int32_t resume_result;
static bool fail_second_deadline;
static int32_t issue(void *c,alarm_sleep_v1 *out){
    int32_t rc=prepare(c,out);if(rc==ALARM_OK)issued=*out;return rc;
}
static int32_t consume(void *c,const alarm_sleep_v1 *ticket){
    (void)c;assert(light_calls==1 && !deep_calls && !panel_resumes && !pmu_resumes && !refreshes);
    assert(!memcmp(ticket,&issued,sizeof(issued)));resumes++;
    if(fail_second_deadline)rtc_bad=true;
    return resume_result;
}
static void current_reset(void){
    motion_reset();resumes=0;resume_result=ALARM_OK;fail_second_deadline=false;
    extended=(alarm_service_sleep_v1){.base=api,.resume_sleep=consume};
    extended.base.struct_size=sizeof(extended);extended.base.prepare_sleep=issue;
}
static int current(unsigned mode){
    return watch_alarm_sleep_motion_prepared(&panel,&pmu,&motion,mode,&extended.base,diagnostic);
}
int main(void){
    (void)legacy_alarm_sleep_test_main;
    for(unsigned mode=0;mode<3;mode++)for(int rc=RISC_LIGHT_SLEEP_RETAINED;rc<0;rc++){
        current_reset();entry_result=rc;(void)current(mode);assert(!resumes);
    }
    current_reset();entry_result=0;assert(current(PORTABLE_SLEEP_LIGHT)==WATCH_SLEEP_WOKE);
    assert(resumes==1 && service_due && refreshes==1 && !deep_calls);
    current_reset();entry_result=0;deadline=0;assert(current(PORTABLE_SLEEP_LIGHT)==WATCH_SLEEP_WOKE);
    assert(resumes==1 && !deep_calls);
    current_reset();entry_result=0;deadline=2000;assert(current(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_RETAINED);
    assert(resumes==1 && deep_calls==1 && duration_seen==700000 && !refreshes);
    current_reset();entry_result=0;deadline=2000;crown=true;assert(current(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_WOKE);
    assert(resumes==1 && !deep_calls && refreshes==1);
    current_reset();entry_result=0;assert(current(PORTABLE_SLEEP_DEEP)==WATCH_SLEEP_RETAINED);
    assert(!resumes && deep_calls==1);
    for(int error=ALARM_BUSY;error>=ALARM_FOREGROUND;error--){
        current_reset();entry_result=0;deadline=2000;resume_result=error;
        assert(current(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_REFUSED);
        assert(resumes==1 && !deep_calls && !refreshes && panel_resumes==1 && pmu_resumes==1);
        assert(watch_sleep_stage==4 && watch_sleep_detail==error && !motion_registered);
    }
    current_reset();entry_result=0;deadline=2000;fail_second_deadline=true;
    assert(current(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_REFUSED);
    assert(resumes==1 && !deep_calls && !refreshes && watch_sleep_stage==4 && watch_sleep_detail==ALARM_RTC);
    current_reset();extended.base.struct_size=sizeof(alarm_service_v1);
    assert(current(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_REFUSED);
    assert(!resumes && !motion_prepares && !light_calls && !deep_calls && !panel_resumes && !pmu_resumes);
    current_reset();extended.resume_sleep=NULL;assert(current(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_REFUSED);
    assert(!resumes && !motion_prepares && !light_calls && !deep_calls);
    current_reset();assert(watch_alarm_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_LIGHT,&api,diagnostic)==WATCH_SLEEP_REFUSED);
    assert(!light_calls && !resumes);
    puts("Current alarm resume adapter: exact ticket, successful Light only, both wake causes, untimed Light, Deep exclusion, retained/refusal, explicit errors and short suffix PASS");
}
