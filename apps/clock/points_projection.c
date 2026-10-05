/* Watch presentation of the Utilities-owned recurrence model. No I/O, output or
 * scheduling authority here. Called with copied catalog/metadata and actual RTC time. */
#include "points_projection.h"
#include "PointsSchedule.h"
#include <string.h>
static bool watch_points_custom(unsigned kind) {
#if WATCH_POINTS_EXTENDED
    return kind==POINTS_CUSTOM_1||kind==POINTS_CUSTOM_2;
#else
    (void)kind;return false;
#endif
}
static void watch_points_style(const points_meta *meta,unsigned kind,nova_point_event *out) {
    out->color_index=6;out->label[0]=0;
#if WATCH_POINTS_EXTENDED
    if(!watch_points_custom(kind))return;
    unsigned index=kind-POINTS_CUSTOM_1;
    if(meta&&index<POINTS_CUSTOM_COUNT&&meta->custom[index].name[0]) {
        out->color_index=meta->custom[index].color<POINTS_COLOR_COUNT?meta->custom[index].color:6;
        unsigned n=0;while(n<NOVA_POINT_LABEL_MAX&&meta->custom[index].name[n])n++;
        if(n)memcpy(out->label,meta->custom[index].name,n);
        out->label[n]=0;
    } else {
        const char *fallback=index?"CUSTOM 2":"CUSTOM 1";unsigned n=0;
        while(n<NOVA_POINT_LABEL_MAX&&fallback[n]){out->label[n]=fallback[n];n++;}out->label[n]=0;
    }
#else
    (void)meta;(void)kind;
#endif
}
static bool watch_points_event(const points_event *e,const points_meta *meta,uint32_t today,nova_point_event *out) {
    twatch_rtc_time_v1 raw,local;uint32_t day;
    if(!points_calendar(e->deadline,&raw)||!portable_time_forward(&raw,&local)||
       !points_local_day(e->deadline,&day))return false;
    *out=(nova_point_event){.at_rtc=e->deadline,.hour=local.hour,.minute=local.minute,.kind=e->kind,
        .source_slot=e->slot,.is_end=e->edge!=0,.day_offset=(int16_t)((int32_t)day-(int32_t)today)};
    watch_points_style(meta,e->kind,out);return true;
}
bool watch_points_projection(const points_config *config,const points_meta *meta,uint32_t now,nova_points_state *out) {
    nova_points_state v={.now_rtc=now,.status=NOVA_POINTS_EMPTY};
    uint32_t today;points_projection projection;
    if(!points_local_day(now,&today)||!points_project(config,now,&projection)) {
        v.status=NOVA_POINTS_ERROR;*out=v;return false;
    }
    if(!config->revision){*out=v;return true;}
    v.status=NOVA_POINTS_READY;
    v.next_count=(uint8_t)projection.count;v.previous_valid=projection.has_previous;
    for(unsigned i=0;i<v.next_count;i++)if(!watch_points_event(&projection.next[i],meta,today,&v.next[i]))goto invalid;
    if(v.previous_valid) {
        if(!watch_points_event(&projection.previous,meta,today,&v.previous))goto invalid;
        unsigned kind=projection.previous.kind;
        v.phase=projection.previous.edge?NOVA_PHASE_UNKNOWN:
            kind==POINTS_WORK_START?NOVA_PHASE_WORKING:kind==POINTS_WORK_END?NOVA_PHASE_OFF_WORK:
            kind==POINTS_LUNCH?NOVA_PHASE_LUNCH:kind==POINTS_BREAK?NOVA_PHASE_BREAK:
            kind==POINTS_BEDTIME?NOVA_PHASE_WIND_DOWN:NOVA_PHASE_UNKNOWN;
    }
    /* Endpoints after midnight belong to yesterday's selected start weekday. */
    for(int offset=-1;offset<=0;offset++) {
        int day=(int)today+offset;if(day<1)continue;
        for(unsigned slot=0;slot<POINTS_MAX;slot++)for(unsigned edge=0;edge<2;edge++) {
            points_event e;nova_point_event item;
            if(!points_event_for_day(config,slot,(uint32_t)day,edge,&e,NULL)||
               !watch_points_event(&e,meta,today,&item)||item.day_offset!=0)continue;
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
        v.work_valid=watch_points_event(&best_start,meta,today,&v.work_start)&&watch_points_event(&best_end,meta,today,&v.work_end);
    }
    if(v.previous_valid&&projection.previous.edge)
        v.phase=v.work_valid&&v.work_start.at_rtc<=now&&now<v.work_end.at_rtc?NOVA_PHASE_WORKING:NOVA_PHASE_UNKNOWN;
    /* A shorter overlapping duration ending must reveal any still-active
     * duration. Custom durations remain semantically custom rather than BREAK. */
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
    if(has_active_duration)v.phase=active_start.kind==POINTS_LUNCH?NOVA_PHASE_LUNCH:
        active_start.kind==POINTS_BREAK?NOVA_PHASE_BREAK:NOVA_PHASE_UNKNOWN;
    if(!v.next_count&&!v.previous_valid&&!v.today_count)v.status=NOVA_POINTS_EMPTY;
    /* Include metadata revision in the presentation stamp so custom label/color
     * edits invalidate schedule cards without changing recurrence. */
    uint32_t meta_revision=0;
#if WATCH_POINTS_EXTENDED
    if(meta)meta_revision=meta->revision;
#else
    (void)meta;
#endif
    v.revision=config->revision ^ (meta_revision*2166136261u) ^ (today*16777619u) ^
        (v.previous_valid?v.previous.at_rtc:0) ^ (v.next_count?v.next[0].at_rtc:0) ^ (uint32_t)v.status;
    *out=v;return true;
invalid:
    v=(nova_points_state){.now_rtc=now,.status=NOVA_POINTS_ERROR};*out=v;return false;
}
