#include <assert.h>
#include <stdio.h>
#include "../apps/clock/points_projection.c"
static uint32_t civil(unsigned year,unsigned month,unsigned day,unsigned hour,unsigned minute) {
 twatch_rtc_time_v1 t={(uint16_t)year,(uint8_t)month,(uint8_t)day,0,(uint8_t)hour,(uint8_t)minute,0};
 t.weekday=(uint8_t)watch_weekday(year,month,day);portable_time_candidate c[2];assert(portable_time_inverse(&t,c)==1);
 uint32_t out;assert(alarm_calendar_seconds(c[0].rtc.year,c[0].rtc.month,c[0].rtc.day,c[0].rtc.hour,c[0].rtc.minute,0,&out));return out;
}
static points_config config(void) {
 points_config c={.revision=1,.created=civil(2026,10,4,0,0)};
 for(unsigned i=0;i<POINTS_MAX;i++)c.points[i]=(points_item){.kind=POINTS_BREAK};
 c.points[0]=(points_item){.kind=POINTS_WORK_START,.enabled=1,.weekdays=127,.hour=8,.minute=30};
 c.points[1]=(points_item){.kind=POINTS_LUNCH,.enabled=1,.weekdays=127,.hour=12,.duration_minutes=60};
 c.points[2]=(points_item){.kind=POINTS_WORK_END,.enabled=1,.weekdays=127,.hour=17};return c;
}
static points_meta meta(void) {
 points_meta m={.revision=1};m.custom[0].color=2;memcpy(m.custom[0].name,"MEDICINE",9);
 m.custom[1].color=7;memcpy(m.custom[1].name,"WALK DOG",9);return m;
}
int main(void) {
 points_config c=config();points_meta m=meta();nova_points_state v,a;
 assert(watch_points_projection(&c,&m,civil(2026,10,4,11,0),&v));
 assert(v.status==NOVA_POINTS_READY&&v.next_count==4&&v.next[0].kind==POINTS_LUNCH&&v.next[1].is_end);
 assert(v.today_count==4&&v.work_valid&&v.work_start.hour==8&&v.work_end.hour==17&&v.phase==NOVA_PHASE_WORKING);
 assert(watch_points_projection(&c,&m,civil(2026,10,4,11,1),&a)&&v.revision==a.revision);
 assert(watch_points_projection(&c,&m,civil(2026,10,4,12,0),&a)&&v.revision!=a.revision&&a.phase==NOVA_PHASE_LUNCH);
 assert(watch_points_projection(&c,&m,civil(2026,10,4,18,0),&v)&&v.work_valid&&v.work_end.day_offset==0&&v.work_end.at_rtc<v.now_rtc);
 c.points[3]=(points_item){.kind=POINTS_BREAK,.enabled=1,.weekdays=127,.hour=12,.minute=15,.duration_minutes=15};
 assert(watch_points_projection(&c,&m,civil(2026,10,4,12,20),&v)&&v.phase==NOVA_PHASE_BREAK);
 assert(watch_points_projection(&c,&m,civil(2026,10,4,12,40),&v)&&v.phase==NOVA_PHASE_LUNCH);
 c.points[3].enabled=0;
 c.points[0].enabled=0;assert(watch_points_projection(&c,&m,civil(2026,10,4,11,0),&v)&&!v.work_valid);
 c.points[1]=(points_item){.kind=POINTS_BREAK,.enabled=1,.weekdays=1,.hour=23,.minute=30,.duration_minutes=120};c.points[2].enabled=0;
 assert(watch_points_projection(&c,&m,civil(2026,10,5,0,15),&v));assert(v.today_count==1&&v.today[0].is_end&&v.next[0].hour==1&&v.next[0].minute==30);
 assert(v.previous_valid&&v.previous.day_offset==-1);
 c=(points_config){0};assert(watch_points_projection(&c,&m,civil(2026,10,4,11,0),&v)&&v.status==NOVA_POINTS_EMPTY);
 c=config();c.points[0].hour=25;assert(!watch_points_projection(&c,&m,civil(2026,10,4,11,0),&v)&&v.status==NOVA_POINTS_ERROR);
 c=config();c.created=civil(2026,3,7,0,0);c.points[0]=(points_item){.kind=POINTS_WORK_START,.enabled=1,.weekdays=127,.hour=1};c.points[2]=(points_item){.kind=POINTS_WORK_END,.enabled=1,.weekdays=127,.hour=4};
 assert(watch_points_projection(&c,&m,civil(2026,3,8,1,15),&v)&&v.work_valid);
#ifdef PORTABLE_RTC_UTC8_DENVER
 assert(v.work_end.at_rtc-v.work_start.at_rtc==7200);
#else
 assert(v.work_end.at_rtc-v.work_start.at_rtc==10800);
#endif
 /* Custom metadata affects presentation only; recurrence and warning cues are
  * not projected as visible schedule edges. */
 c=(points_config){.revision=7,.created=civil(2026,10,4,0,0)};
 c.points[0]=(points_item){.kind=POINTS_CUSTOM_1,.enabled=1,.mode=3,.weekdays=127,.hour=14,.duration_minutes=30,.notify_end=1,.warn3=1};
 assert(watch_points_projection(&c,&m,civil(2026,10,4,13,0),&v)&&v.next_count==2);
 assert(v.next[0].kind==NOVA_POINT_CUSTOM_1&&!strcmp(v.next[0].label,"MEDICINE")&&v.next[0].color_index==2&&!v.next[0].is_end);
 assert(v.next[1].is_end&&v.next[1].at_rtc-v.next[0].at_rtc==1800);
 assert(watch_points_projection(&c,&m,civil(2026,10,4,13,1),&a)&&v.revision==a.revision);
 m.revision++;m.custom[0].color=7;assert(watch_points_projection(&c,&m,civil(2026,10,4,13,1),&a)&&v.revision!=a.revision&&a.next[0].color_index==7);
 puts("Points projection: live/custom schedule, stable cache, midnight parent day, empty/error and real DST work bounds passed");
}
