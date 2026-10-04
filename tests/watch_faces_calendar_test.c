/* Calendar collection unit and guarded raster tests, using production code. */
#include "apps/clock/nova/nova.c"
#ifndef WATCH_CALENDAR_COLLECTION_RENDER_INCLUDED
#include "apps/clock/faces/calendar_collection.inc"
#endif
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
static uint8_t pixels[240*488+32];
static void render(nova_watch_state*s,unsigned id) {
    memset(pixels,0xa5,sizeof(pixels));canvas c={pixels+16,488};
    for(unsigned y=0;y<240;y++)memset(at(&c,0,y),0,480);
    nova_watch_labels l;nova_watch_format(s,&l);
    unsigned sub=s->subsecond_ms<1000?s->subsecond_ms:999;
    fcalendar_collection(&c,s,&l,id,0,0,0,sub);
    for(unsigned i=0;i<16;i++)assert(pixels[i]==0xa5&&pixels[sizeof(pixels)-i-1]==0xa5);
    for(unsigned y=0;y<240;y++)for(unsigned x=480;x<488;x++)assert(pixels[16+y*488+x]==0xa5);
}
unsigned calendar_date(unsigned y,unsigned m,unsigned d,unsigned which) {
    return which==0?fc_weekday(y,m,d):which==1?fc_day_of_year(y,m,d):which==2?fc_iso_week(y,m,d):fc_days_in_month(y,m);
}
unsigned calendar_shift(unsigned y,unsigned m,unsigned d,int delta) {
    fc_shift_date(&y,&m,&d,delta);return y*10000+m*100+d;
}
void calendar_render_frame(uint8_t*out,unsigned id,unsigned year,unsigned month,unsigned day,unsigned hour,unsigned minute,unsigned second,unsigned valid,unsigned battery,unsigned hour_24) {
    nova_watch_state s={.time={(uint16_t)year,(uint8_t)month,(uint8_t)day,0,(uint8_t)hour,(uint8_t)minute,(uint8_t)second},.time_valid=valid!=0,.battery_valid=battery<=100,.battery_percent=(uint8_t)battery,.subsecond_ms=250,.animation_ms=42000,.hour_24=hour_24!=0};
    render(&s,id);for(unsigned y=0;y<240;y++)memcpy(out+y*480,pixels+16+y*488,480);
}
int main(int argc,char**argv) {
    nova_watch_state s={.time={2026,10,4,0,10,42,18},.time_valid=true,.battery_valid=true,.battery_percent=84,.subsecond_ms=250,.animation_ms=42000};
    char hour_label[3];fc_hour_label(hour_label,0,false);assert(!strcmp(hour_label,"12"));fc_hour_label(hour_label,18,false);assert(!strcmp(hour_label,"06"));fc_hour_label(hour_label,24,false);assert(!strcmp(hour_label,"12"));fc_hour_label(hour_label,0,true);assert(!strcmp(hour_label,"00"));fc_hour_label(hour_label,18,true);assert(!strcmp(hour_label,"18"));
    assert(fc_leap(2000)&&!fc_leap(1900)&&!fc_leap(2100)&&fc_leap(2400));
    assert(fc_day_of_year(2024,2,29)==60&&fc_day_of_year(2024,12,31)==366&&fc_day_of_year(2025,12,31)==365);
    assert(fc_iso_week(2021,1,1)==53&&fc_iso_week(2019,12,30)==1&&fc_iso_week(2026,10,4)==40);
    assert(calendar_shift(2000,1,1,-3)==19991229&&calendar_shift(2099,12,31,3)==21000103);
    for(unsigned id=0;id<8;id++) {
        render(&s,id);
        if(argc>1){char path[512];snprintf(path,sizeof(path),"%s/face-%u.rgb565",argv[1],id);FILE*f=fopen(path,"wb");assert(f);for(unsigned y=0;y<240;y++)assert(fwrite(pixels+16+y*488,1,480,f)==480);fclose(f);}
        /* RTC weekday is untrusted but bounded. Date-derived pixels stay exact. */
        uint8_t previous[sizeof(pixels)];memcpy(previous,pixels,sizeof(pixels));s.time.weekday=6;render(&s,id);assert(!memcmp(previous,pixels,sizeof(pixels)));s.time.weekday=0;
        s.time_valid=false;s.battery_valid=false;render(&s,id);
        /* Unknown dates cannot vary with stale but valid RTC fields. */
        memcpy(previous,pixels,sizeof(pixels));s.time=(twatch_rtc_time_v1){2047,8,21,3,20,7,38};render(&s,id);assert(!memcmp(previous,pixels,sizeof(pixels)));
        s.time=(twatch_rtc_time_v1){2026,10,4,0,10,42,18};s.time_valid=true;s.battery_valid=true;
        s.subsecond_ms=65535;s.animation_ms=UINT32_MAX;render(&s,id);s.subsecond_ms=250;s.animation_ms=42000;
    }
    /* Earliest/latest supported years and leap/date rollovers. */
    static const unsigned dates[][3]={{2000,1,1},{2000,2,29},{2020,12,31},{2021,1,1},{2024,2,29},{2026,2,1},{2026,8,31},{2099,12,31}};
    for(unsigned i=0;i<sizeof(dates)/sizeof(dates[0]);i++)for(unsigned hour=0;hour<=23;hour+=23){s.time.year=(uint16_t)dates[i][0];s.time.month=(uint8_t)dates[i][1];s.time.day=(uint8_t)dates[i][2];s.time.hour=(uint8_t)hour;s.time.minute=59;s.time.second=59;for(unsigned id=0;id<8;id++)render(&s,id);}
    for(unsigned m=0;m<=100;m+=25){s.battery_percent=(uint8_t)m;for(unsigned id=0;id<8;id++)render(&s,id);}
    s.battery_percent=255;s.time.month=0;for(unsigned id=0;id<8;id++)render(&s,id);
    puts("Calendar: eight faces, Gregorian/ISO boundaries, RTC-derived weekdays, unknown state, leap dates, battery range and stride guards passed");
}
