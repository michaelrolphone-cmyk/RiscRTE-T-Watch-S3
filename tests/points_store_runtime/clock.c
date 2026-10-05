#include <assert.h>
#define app_main actual_clock_main
#include POINTS_CLOCK_SOURCE
#undef app_main
extern int points_test_written_yet(void);
__attribute__((visibility("default"))) void app_main(void) {
    if(!points_test_written_yet()) {
        const risc_runtime_api_v1* api=risc_runtime_get_api(1);
        assert(api&&api->request_launch&&api->request_launch("points_in_time.elf"));return;
    }
    actual_clock_main();
}
__attribute__((visibility("default"))) void points_test_snapshot(unsigned* s) {
    s[0]=picker.selected;s[1]=face.hour_24;s[2]=clock_points_view.status;
    s[3]=clock_points_view.today_count;s[4]=clock_points_view.next_count;
    s[5]=clock_points_config.revision;s[6]=clock_points_meta.custom[0].color;
    s[7]=clock_points_meta.custom[1].color;s[8]=!strcmp(clock_points_meta.custom[0].name,"FOCUS");
    s[9]=!strcmp(clock_points_meta.custom[1].name,"WALK");
    s[10]=0;s[11]=0;
    for(unsigned i=0;i<clock_points_view.today_count;i++) {
        s[10]+=clock_points_view.today[i].is_end;
        s[11]+=clock_points_view.today[i].kind>=6;
    }
}
