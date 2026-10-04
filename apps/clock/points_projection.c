/* Watch presentation of the Utilities-owned recurrence model. No I/O, output or
 * scheduling authority here. Called with a copied catalog and actual RTC time. */
#include "PointsSchedule.h"
#include "faces/points_state.h"
#include <string.h>
static bool watch_points_event(const points_event *e,uint32_t today,nova_point_event *out) {
    twatch_rtc_time_v1 raw,local;uint32_t day;
    if(!points_calendar(e->deadline,&raw)||!portable_time_forward(&raw,&local)||
       !points_local_day(e->deadline,&day))return false;
    *out=(nova_point_event){.at_rtc=e->deadline,.hour=local.hour,.minute=local.minute,.kind=e->kind,.source_slot=e->slot,.is_end=e->edge!=0,.day_offset=(int16_t)((int32_t)day-(int32_t)today)};
    return true;
}
bool watch_points_projection(const points_config *config,uint32_t now,nova_points_state *out) {
    nova_points_state v={.now_rtc=now,.status=NOVA_POINTS_EMPTY};
    uint32_t today;points_projection projection;
    if(!points_local_day(now,&today)||!points_project(config,now,&projection)) {
        v.status=NOVA_POINTS_ERROR;*out=v;return false;
    }
    if(!config->revision){*out=v;return true;}
    v.status=NOVA_POINTS_READY;
    v.next_count=(uint8_t)projection.count;v.previous_valid=projection.has_previous;
    for(unsigned i=0;i<v.next_count;i++)if(!watch_points_event(&projection.next[i],today,&v.next[i]))goto invalid;
    if(v.previous_valid) {
        if(!watch_points_event(&projection.previous,today,&v.previous))goto invalid;
        unsigned kind=projection.previous.kind;
        v.phase=projection.previous.edge?NOVA_PHASE_WORKING:
            kind==POINTS_WORK_START?NOVA_PHASE_WORKING:kind==POINTS_WORK_END?NOVA_PHASE_OFF_WORK:
            kind==POINTS_LUNCH?NOVA_PHASE_LUNCH:kind==POINTS_BREAK?NOVA_PHASE_BREAK:NOVA_PHASE_WIND_DOWN;
    }
    /* Endpoints after midnight belong to yesterday's selected start weekday. */
    for(int offset=-1;offset<=0;offset++) {
        int day=(int)today+offset;if(day<1)continue;
        for(unsigned slot=0;slot<POINTS_MAX;slot++)for(unsigned edge=0;edge<2;edge++) {
            points_event e;nova_point_event item;
            if(!points_event_for_day(config,slot,(uint32_t)day,edge,&e,NULL)||
               !watch_points_event(&e,today,&item)||item.day_offset!=0)continue;
            if(v.today_count>=NOVA_POINTS_TODAY_MAX)goto invalid;
            unsigned at=v.today_count++;
            while(at&&v.today[at-1].at_rtc>item.at_rtc){v.today[at]=v.today[at-1];--at;}
            v.today[at]=item;
        }
    }
    /* Use a real current/upcoming Work Start followed by its first Work End.
     * An unpaired start never produces an invented workday progress bar. */
    points_event best_start={0},best_end={0};bool paired=false;unsigned best_rank=5;
    for(int offset=-1;offset<=7;offset++) {
        int day=(int)today+offset;if(day<1||day>36525)continue;
        for(unsigned slot=0;slot<POINTS_MAX;slot++) {
            if(config->points[slot].kind!=POINTS_WORK_START)continue;
            points_event start,end={0};bool found_end=false;
            if(!points_event_for_day(config,slot,(uint32_t)day,0,&start,NULL))continue;
            for(unsigned ahead=0;ahead<=1;ahead++)for(unsigned j=0;j<POINTS_MAX;j++) {
                points_event e;if(config->points[j].kind!=POINTS_WORK_END||
                    !points_event_for_day(config,j,(uint32_t)day+ahead,0,&e,NULL)||e.deadline<=start.deadline)continue;
                if(!found_end||e.deadline<end.deadline){end=e;found_end=true;}
            }
            if(!found_end)continue;
            unsigned rank=start.deadline<=now&&end.deadline>now?0:
                (uint32_t)day==today&&start.deadline>now?1:
                (uint32_t)day==today&&end.deadline<=now?2:start.deadline>now?3:4;
            if(rank==4)continue;
            if(!paired||rank<best_rank||(rank==best_rank&&
               (rank==2?start.deadline>best_start.deadline:start.deadline<best_start.deadline))) {
                best_start=start;best_end=end;paired=true;best_rank=rank;
            }
        }
    }
    if(paired) {
        v.work_valid=watch_points_event(&best_start,today,&v.work_start)&&watch_points_event(&best_end,today,&v.work_end);
    }
    if(v.previous_valid&&projection.previous.edge)
        v.phase=v.work_valid&&v.work_start.at_rtc<=now&&now<v.work_end.at_rtc?NOVA_PHASE_WORKING:NOVA_PHASE_UNKNOWN;
    /* A shorter overlapping break ending must reveal the still-active lunch,
     * rather than declaring work resumed just because BACK was the last edge. */
    points_event active_start={0};bool has_active_duration=false;
    for(int offset=-1;offset<=0;offset++) {
        int day=(int)today+offset;if(day<1)continue;
        for(unsigned slot=0;slot<POINTS_MAX;slot++) {
            points_event start,end;
            if(!config->points[slot].duration_minutes||
               !points_event_for_day(config,slot,(uint32_t)day,0,&start,NULL)||
               !points_event_for_day(config,slot,(uint32_t)day,1,&end,NULL)||
               start.deadline>now||end.deadline<=now)continue;
            if(!has_active_duration||points_event_before(&active_start,&start)) {
                active_start=start;has_active_duration=true;
            }
        }
    }
    if(has_active_duration)v.phase=active_start.kind==POINTS_LUNCH?NOVA_PHASE_LUNCH:NOVA_PHASE_BREAK;
    if(!v.next_count&&!v.previous_valid&&!v.today_count)v.status=NOVA_POINTS_EMPTY;
    /* A copied, stable cache stamp: seconds advance countdown but do not
     * invalidate all nonfocused previews. Local-day/event changes do. */
    v.revision=config->revision ^ (today*16777619u) ^
        (v.previous_valid?v.previous.at_rtc:0) ^ (v.next_count?v.next[0].at_rtc:0) ^ (uint32_t)v.status;
    *out=v;return true;
invalid:
    v=(nova_points_state){.now_rtc=now,.status=NOVA_POINTS_ERROR};*out=v;return false;
}
