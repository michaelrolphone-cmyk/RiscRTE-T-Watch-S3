/* Drive the real application's load/save business logic through Runtime's
 * production app policy. Input/render loop is covered separately by GUI tests. */
#include <assert.h>
#define app_main unused_points_ui_main
#include POINTS_APP_SOURCE
#undef app_main
extern int points_test_case(void);
extern int points_test_format(void);
extern void points_test_written(void);
__attribute__((visibility("default"))) void app_main(void) {
    assert(open_dependencies());ready=true;load_catalog();
    assert(writer.loaded&&clock_valid&&service_valid);
    int which=points_test_case();
    if(which&&which!=8) {
        selected=0;draft=(points_item){.kind=POINTS_LUNCH,.enabled=1,.mode=1,.weekdays=127,.hour=12,.duration_minutes=30};
        if(which==2||which>=3){draft.notify_end=which!=7;draft.warn3=which!=6;}
        if(which==3){draft.kind=POINTS_CUSTOM_1;}
        save_action();assert(writer.saved.revision==1&&!writer.uncertain);
        if(which==3) {
            selected=1;draft.kind=POINTS_CUSTOM_2;draft.hour=13;save_action();
            assert(writer.saved.revision==2);
            points_meta meta={.revision=1,.custom={{.color=3,.name="FOCUS"},{.color=7,.name="WALK"}}};
            assert(points_writer_save_meta(&writer,storage,&meta)==ALARM_OK);
        }
    }
    /* Simulate an explicit latest Settings change while Clock is away. */
    if(which!=8)assert(portable_time_format_save(preferences,(unsigned)points_test_format()));
    /* Reconcile through the real provider's bound storage before leaving. */
    for(unsigned i=0;i<64;i++) {
        assert(service->step(service->context)>=ALARM_OK);
        refresh_status();
        if(service_state.state==ALARM_STATE_READY)break;
    }
    assert(service_state.state==ALARM_STATE_READY);
    close_dependencies();points_test_written();
}
/* The unused event loop is linked for source fidelity, never invoked here. */
const t5_app_api_v1 *t5_app_get_api(uint32_t version) {(void)version;assert(!"UI event loop is outside this source-wired save fixture");return NULL;}
