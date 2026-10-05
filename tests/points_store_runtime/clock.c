#include <assert.h>
#define app_main actual_clock_main
#include POINTS_CLOCK_SOURCE
#undef app_main
extern int points_test_written_yet(void);
extern int points_test_case(void);
extern int points_test_option(const char*,int);
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
    s[12]=!strcmp(clock_points_meta.custom[0].name,"Drive to Work");
    s[13]=!strcmp(clock_points_meta.custom[1].name,"Wakeup");
#if defined(POINTS_DEFAULTS_AVAILABLE)
    if(points_test_case()==8||points_test_case()==14) {
        const unsigned kinds[]={7,6,1,4,3,4,2},hour[]={4,5,6,9,12,14,16};
        const unsigned minute[]={30,30,0,0,0,15,30},duration[]={0,15,0,15,30,15,0};
        for(unsigned i=0;i<7;i++) {
            const points_item *p=&clock_points_config.points[i];
            assert(p->kind==kinds[i]&&p->hour==hour[i]&&p->minute==minute[i]);
            assert(p->enabled&&p->weekdays==30&&p->mode==3&&p->duration_minutes==duration[i]);
            assert(!p->notify_end&&p->warn3==(i==3||i==4||i==5));
        }
        assert(s[12]&&s[13]);
        for(unsigned i=1;i<clock_points_view.today_count;i++)
            assert(clock_points_view.today[i-1].at_rtc<clock_points_view.today[i].at_rtc);
        const unsigned hours[]={4,5,5,6,9,9,12,12,14,14,16};
        const unsigned minutes[]={30,30,45,0,0,15,0,30,15,30,30};
        for(unsigned i=0;i<clock_points_view.today_count;i++) {
            assert(clock_points_view.today[i].hour==hours[i]&&clock_points_view.today[i].minute==minutes[i]);
            if(clock_points_view.today[i].source_slot==1)assert(!strcmp(clock_points_view.today[i].label,"Drive to Work"));
        }
    }
#endif
    for(unsigned i=0;i<clock_points_view.today_count;i++) {
        s[10]+=clock_points_view.today[i].is_end;
        s[11]+=clock_points_view.today[i].kind>=6;
    }
}
