/* Drive the real application's load/save business logic through Runtime's
 * production app policy. Input/render loop is covered separately by GUI tests. */
#include <assert.h>
#define app_main unused_points_ui_main
#include POINTS_APP_SOURCE
#undef app_main
extern int points_test_case(void);
extern int points_test_format(void);
extern void points_test_written(void);
extern int points_test_option(const char*,int);
static void check_defaults(void) {
    const unsigned kinds[]={7,6,1,4,3,4,2},hour[]={4,5,6,9,12,14,16};
    const unsigned minute[]={30,30,0,0,0,15,30},duration[]={0,15,0,15,30,15,0};
    for(unsigned i=0;i<7;i++) {
        const points_item *p=&writer.saved.points[i];
        assert(p->kind==kinds[i]&&p->hour==hour[i]&&p->minute==minute[i]);
        assert(p->enabled&&p->weekdays==30&&p->mode==3&&p->duration_minutes==duration[i]);
        assert(!p->notify_end&&p->warn3==(i==3||i==4||i==5));
    }
    assert(!writer.saved.points[7].kind&&!writer.saved.created&&writer.saved.revision==1);
    assert(!strcmp(writer.meta.custom[0].name,"Drive to Work")&&!strcmp(writer.meta.custom[1].name,"Wakeup"));
}
__attribute__((visibility("default"))) void app_main(void) {
    assert(open_dependencies());ready=true;load_catalog();
    assert(writer.loaded&&clock_valid&&service_valid);
    int which=points_test_case();
    if((which>=1&&which<=7)||(which>=10&&which<=12)) {
        selected=0;draft=(points_item){.kind=POINTS_LUNCH,.enabled=1,.mode=1,.weekdays=127,.hour=12,.duration_minutes=30};
        if(which==2||which>=3){draft.notify_end=which!=7;draft.warn3=which!=6;}
        if(which==3||which>=10){draft.kind=POINTS_CUSTOM_1;}
        save_action();assert(writer.saved.revision==2&&!writer.uncertain);
        if(which==3||which>=10) {
            selected=1;draft.kind=POINTS_CUSTOM_2;draft.hour=13;save_action();
            assert(writer.saved.revision==3);
            points_meta meta={.revision=1,.custom={{.color=3,.name="FOCUS"},{.color=7,.name="WALK"}}};
            if(which>=10)strcpy(meta.custom[0].name,"Drive to Work");
            assert(points_writer_save_meta(&writer,storage,&meta)==ALARM_OK);
        }
    }
    /* Simulate an explicit latest Settings change while Clock is away. */
    if(which!=8&&which!=14)assert(portable_time_format_save(preferences,(unsigned)points_test_format()));
    if(which==8||which==14)check_defaults();
    if(which==9){assert(writer.saved.revision==1&&writer.saved.points[0].kind==POINTS_LUNCH);}
    /* Reconcile through the real provider's bound storage before leaving. */
    for(unsigned i=0;i<64;i++) {
        assert(service->step(service->context)>=ALARM_OK);
        refresh_status();
        if(service_state.state==ALARM_STATE_READY)break;
    }
    assert(service_state.state==ALARM_STATE_READY);
    if(which==8||which==14) {
        /* Advance the actual cue state machine, including its 350ms close. */
        if(which==14)for(unsigned i=0;i<200;i++) {
            assert(service->step(service->context)>=ALARM_OK);runtime->yield_ms(10);
        }
        alarm_sleep_v1 sleep={.struct_size=sizeof(sleep)};int32_t rc=ALARM_PENDING;
        for(unsigned i=0;i<128&&rc==ALARM_PENDING;i++) {
            rc=service->prepare_sleep(service->context,&sleep);
            if(rc==ALARM_PENDING)assert(service->step(service->context)>=ALARM_OK);
        }
        assert(rc==ALARM_OK&&sleep.deadline>sleep.rtc_seconds);
        int delta=points_test_option("POINTS_NEXT_MINUTES",-1);
        if(delta>=0)assert(sleep.deadline-sleep.rtc_seconds==(uint32_t)delta*60);
    }
    close_dependencies();points_test_written();
}
/* The unused event loop is linked for source fidelity, never invoked here. */
const t5_app_api_v1 *t5_app_get_api(uint32_t version) {(void)version;assert(!"UI event loop is outside this source-wired save fixture");return NULL;}
