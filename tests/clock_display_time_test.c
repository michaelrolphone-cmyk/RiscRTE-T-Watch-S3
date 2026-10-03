#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "apps/clock/display_time.h"
static void check(unsigned y,unsigned m,unsigned d,unsigned h,unsigned minute,unsigned second,
                  unsigned ey,unsigned em,unsigned ed,unsigned eh,unsigned emin,unsigned es) {
    twatch_rtc_time_v1 rtc={(uint16_t)y,(uint8_t)m,(uint8_t)d,0,(uint8_t)h,(uint8_t)minute,(uint8_t)second};
    twatch_rtc_time_v1 saved=rtc,out={0};
    assert(watch_display_time(&rtc,&out));assert(!memcmp(&saved,&rtc,sizeof(rtc)));
    assert(out.year==ey&&out.month==em&&out.day==ed&&out.hour==eh&&out.minute==emin&&out.second==es);
    assert(out.weekday==watch_weekday(ey,em,ed));
    assert(watch_display_time(&rtc,&rtc));assert(!memcmp(&rtc,&out,sizeof(out)));
}
int main(int argc,char **argv) {
    if(argc==2) {
        assert(!strcmp(argv[1],"oracle"));
        for(unsigned y=2000;y<=2099;y++)for(unsigned m=1;m<=12;m++)
        for(unsigned d=1;d<=watch_month_days(y,m);d++)for(unsigned h=0;h<24;h++) {
            twatch_rtc_time_v1 rtc={(uint16_t)y,(uint8_t)m,(uint8_t)d,0,(uint8_t)h,37,49},out={0};
            bool valid=watch_display_time(&rtc,&out);
            uint8_t row[]={valid,(uint8_t)(out.year>>8),(uint8_t)out.year,out.month,out.day,out.weekday,out.hour,out.minute,out.second};
            assert(fwrite(row,1,sizeof(row),stdout)==sizeof(row));
        }
        return 0;
    }
    check(2026,10,4,0,40,0,2026,10,3,10,40,0); /* observed next-day RTC */
    check(2026,1,4,0,40,0,2026,1,3,9,40,0);   /* winter is -15h, not -14h */
    check(2026,3,8,16,59,59,2026,3,8,1,59,59);
    check(2026,3,8,17,0,0,2026,3,8,3,0,0);
    check(2026,11,1,15,59,59,2026,11,1,1,59,59);
    check(2026,11,1,16,0,0,2026,11,1,1,0,0);
    check(2006,4,2,16,59,59,2006,4,2,1,59,59);
    check(2006,4,2,17,0,0,2006,4,2,3,0,0);
    check(2006,10,29,15,59,59,2006,10,29,1,59,59);
    check(2006,10,29,16,0,0,2006,10,29,1,0,0);
    check(2024,3,1,1,2,3,2024,2,29,10,2,3);
    check(2025,3,1,1,2,3,2025,2,28,10,2,3);
    check(2026,1,1,1,2,3,2025,12,31,10,2,3);
    twatch_rtc_time_v1 rtc={2000,1,1,6,14,59,59},out={0};
    assert(!watch_display_time(&rtc,&out));rtc.hour=15;assert(watch_display_time(&rtc,&out));
    assert(out.year==2000&&out.month==1&&out.day==1&&out.hour==0);
    rtc.day=32;assert(!watch_display_time(&rtc,&out));
    assert(!watch_display_time(NULL,&out));assert(!watch_display_time(&rtc,NULL));
    puts("Configured UTC+08 to America/Denver: observed date, summer/winter, DST boundaries, leap/year and no-write checks passed");
}
