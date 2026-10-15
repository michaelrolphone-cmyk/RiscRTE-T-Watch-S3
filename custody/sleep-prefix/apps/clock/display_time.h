#pragma once
#include "twatch_calendar.h"
/* Temporary explicit app policy until shared Settings owns the time basis:
 * the configured RTC contains fixed UTC+08 wall time; display America/Denver.
 * No RTC write, host time, compiler timestamp or inferred hardware timezone.
 * US rules from IANA tzdb2026e apply over the supported 2000..2099 domain. */
#define WATCH_RTC_UTC_OFFSET_HOURS 8
static inline unsigned watch_month_days(unsigned y,unsigned m) {
    static const uint8_t days[]={31,28,31,30,31,30,31,31,30,31,30,31};
    return days[m-1]+(m==2 && y%4==0 && (y%100!=0 || y%400==0));
}
static inline unsigned watch_weekday(unsigned y,unsigned m,unsigned d) {
    static const uint8_t offsets[]={0,3,2,5,0,3,5,1,4,6,2,4};
    y-=m<3;
    return (y+y/4-y/100+y/400+offsets[m-1]+d)%7;
}
static inline void watch_subtract_hours(twatch_rtc_time_v1 *t,unsigned hours) {
    int hour=(int)t->hour-(int)hours;
    while(hour<0) {
        hour+=24;
        if(t->day>1)t->day--;
        else {
            if(t->month>1)t->month--;
            else{t->month=12;t->year--;}
            t->day=(uint8_t)watch_month_days(t->year,t->month);
        }
    }
    t->hour=(uint8_t)hour;
    t->weekday=(uint8_t)watch_weekday(t->year,t->month,t->day);
}
static inline bool watch_denver_dst(const twatch_rtc_time_v1 *utc) {
    unsigned start_month=utc->year>=2007?3:4;
    unsigned end_month=utc->year>=2007?11:10;
    unsigned first_sunday=1+(7-watch_weekday(utc->year,start_month,1))%7;
    unsigned start_day=first_sunday+(utc->year>=2007?7:0);
    unsigned end_day;
    if(utc->year>=2007)end_day=1+(7-watch_weekday(utc->year,end_month,1))%7;
    else {
        unsigned last=watch_month_days(utc->year,end_month);
        end_day=last-watch_weekday(utc->year,end_month,last);
    }
    /* Start at 02:00 MST (09:00 UTC); end at 02:00 MDT (08:00 UTC).
     * Comparing UTC avoids the spring gap and repeated autumn local hour. */
    bool after_start=utc->month>start_month || (utc->month==start_month &&
        (utc->day>start_day || (utc->day==start_day && utc->hour>=9)));
    bool before_end=utc->month<end_month || (utc->month==end_month &&
        (utc->day<end_day || (utc->day==end_day && utc->hour<8)));
    return after_start && before_end;
}
static inline bool watch_display_time(const twatch_rtc_time_v1 *rtc,
                                      twatch_rtc_time_v1 *display) {
    if(!display || !tw_valid_time(rtc))return false;
    twatch_rtc_time_v1 utc=*rtc;
    watch_subtract_hours(&utc,WATCH_RTC_UTC_OFFSET_HOURS);
    twatch_rtc_time_v1 local=utc;
    watch_subtract_hours(&local,watch_denver_dst(&utc)?6:7);
    if(!tw_valid_time(&local))return false;
    *display=local;
    return true;
}
