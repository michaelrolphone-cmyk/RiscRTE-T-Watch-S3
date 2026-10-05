/* Production renderer fixtures: every scheduled edge below is TEST INPUT.
 * Firmware gets these fields exclusively from persisted daily recurrence. */
#define WATCH_FACE_RENDER_TEST 1
#include "apps/clock/nova/nova.c"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
static uint8_t guarded[240*488+32],tight[240*480],compare[240*480];
static nova_watch_picker_cache cache;
static nova_point_event event(uint32_t base,unsigned hour,unsigned minute,unsigned kind,bool end) {
    return (nova_point_event){.at_rtc=base+hour*3600+minute*60,.hour=(uint8_t)hour,.minute=(uint8_t)minute,.kind=(uint8_t)kind,.source_slot=(uint8_t)kind,.is_end=end};
}
static void fixture(nova_watch_state*s,nova_points_state*p,unsigned scenario) {
    const uint32_t base=844473600; /* Synthetic fixture RTC-day origin. */
    *s=(nova_watch_state){.time={2026,10,4,0,10,42,18},.time_valid=true,.battery_valid=true,.battery_percent=84,.subsecond_ms=250,.animation_ms=42000,.points=p};
    *p=(nova_points_state){.revision=1,.now_rtc=base+10*3600+42*60+18,.status=NOVA_POINTS_READY,.phase=NOVA_PHASE_WORKING,.previous_valid=true,.work_valid=true,.next_count=4,.today_count=7};
    p->today[0]=event(base,8,30,NOVA_POINT_WORK_START,false);
    p->today[1]=event(base,10,15,NOVA_POINT_BREAK,false);
    p->today[2]=event(base,10,30,NOVA_POINT_BREAK,true);
    p->today[3]=event(base,12,0,NOVA_POINT_LUNCH,false);
    p->today[4]=event(base,13,0,NOVA_POINT_LUNCH,true);
    p->today[5]=event(base,17,0,NOVA_POINT_WORK_END,false);
    p->today[6]=event(base,22,30,NOVA_POINT_BEDTIME,false);
    p->previous=p->today[2];for(unsigned i=0;i<4;i++)p->next[i]=p->today[i+3];
    p->work_start=p->today[0];p->work_end=p->today[5];
    if(scenario==1)*p=(nova_points_state){.status=NOVA_POINTS_EMPTY};
    if(scenario==2)s->points=NULL;
    if(scenario==3)p->status=NOVA_POINTS_ERROR;
    if(scenario==4)s->time_valid=false;
    if(scenario==5)p->work_valid=false;
    if(scenario==6){for(unsigned i=0;i<4;i++){p->next[i].at_rtc+=3*86400;p->next[i].day_offset=3;}p->today_count=0;}
    if(scenario==7){ /* Fall-back: wall-clock next goes backward; absolute stays forward. */
        s->time=(twatch_rtc_time_v1){2026,11,1,0,1,45,0};p->now_rtc=base+6300;
        p->previous=event(base,1,30,NOVA_POINT_WORK_START,false);
        p->next_count=1;p->next[0]=event(base,1,15,NOVA_POINT_LUNCH,false);p->next[0].at_rtc=p->now_rtc+1800;
        p->today_count=2;p->today[0]=p->previous;p->today[1]=p->next[0];p->work_start=p->previous;p->work_end=event(base,9,30,NOVA_POINT_WORK_END,false);p->work_end.at_rtc+=3600;
    }
    if(scenario==8){s->time.hour=23;s->time.minute=59;s->time.second=50;p->now_rtc=base+86390;p->previous=p->today[6];p->next_count=1;p->next[0]=event(base+86400,0,0,NOVA_POINT_WORK_START,false);p->next[0].day_offset=1;p->phase=NOVA_PHASE_WIND_DOWN;}
    if(scenario==9)s->battery_valid=false;
    if(scenario==10){s->time.hour=12;s->time.minute=s->time.second=0;p->now_rtc=base+12*3600;p->previous=p->today[3];p->next_count=3;for(unsigned i=0;i<3;i++)p->next[i]=p->today[i+4];p->phase=NOVA_PHASE_LUNCH;}
    if(scenario==11){s->time.hour=s->time.minute=s->time.second=0;p->now_rtc=base;p->previous_valid=false;p->phase=NOVA_PHASE_UNKNOWN;for(unsigned i=0;i<4;i++)p->next[i]=p->today[i];}
    if(scenario==12)s->hour_24=true;
    if(scenario==13){p->today_count=16;for(unsigned i=0;i<16;i++)p->today[i]=event(base,11,i/2,i%4<2?NOVA_POINT_LUNCH:NOVA_POINT_BREAK,i%2!=0);}
    if(scenario==14)p->next[0].at_rtc=p->now_rtc-1;
    if(scenario==15){p->previous_valid=false;p->phase=NOVA_PHASE_UNKNOWN;}
    if(scenario==16){s->time.hour=23;s->time.minute=30;s->time.second=0;p->now_rtc=base+84600;p->previous=event(base,22,0,NOVA_POINT_WORK_START,false);p->work_start=p->previous;p->work_end=event(base+86400,6,0,NOVA_POINT_WORK_END,false);p->work_end.day_offset=1;p->next_count=1;p->next[0]=p->work_end;}
    if(scenario==17){p->next_count=1;p->next[0]=event(base,10,45,NOVA_POINT_BREAK,true);p->previous=event(base,10,30,NOVA_POINT_BREAK,false);p->phase=NOVA_PHASE_BREAK;}
}
static void guarded_render(nova_watch_state*s,unsigned face) {
    memset(guarded,0xa5,sizeof(guarded));memset(tight,0,sizeof(tight));
    risc_display_surface_v1 a={0,guarded+16,240,240,488,240*488,5},b={0,tight,240,240,480,sizeof(tight),5};
    assert(nova_watch_face_render(&a,s,face));assert(nova_watch_face_render(&b,s,face));
    for(unsigned y=0;y<240;y++){assert(!memcmp(guarded+16+y*488,tight+y*480,480));for(unsigned x=480;x<488;x++)assert(guarded[16+y*488+x]==0xa5);}
    for(unsigned i=0;i<16;i++)assert(guarded[i]==0xa5&&guarded[sizeof(guarded)-1-i]==0xa5);
}
void points_render_frame(void*out,unsigned face,unsigned scenario) {
    nova_watch_state s;nova_points_state p;fixture(&s,&p,scenario);guarded_render(&s,face+24);memcpy(out,tight,sizeof(tight));
}
int main(int argc,char**argv) {
    char text[24];
    /* A 12-hour preference must never turn an elapsed duration into wall time. */
    ps_duration(text,13*3600+5*60,false);assert(!strcmp(text,"13:05:00"));
    const uint32_t durations[]={0,59,60,3599,3600,97200,UINT32_MAX};
    const char*full[]={"00:00","00:59","01:00","59:59","1:00:00","27:00:00","1193046:28:15"};
    const char*compact[]={"0:00","0:00","0:01","0:59","1:00","27:00","1193046:28"};
    for(unsigned i=0;i<COUNT(durations);i++){ps_duration(text,durations[i],false);assert(!strcmp(text,full[i]));ps_duration(text,durations[i],true);assert(!strcmp(text,compact[i]));}
    assert(ps_fraction(0,0,UINT32_MAX)==0&&ps_fraction(UINT32_MAX,0,UINT32_MAX)==1024);
    assert(ps_fraction(3600,0,7200)==512&&ps_fraction(3600,7200,0)==0);
    for(uint32_t i=1;i<4000000000u;i+=11111111u){unsigned reference=(unsigned)((uint64_t)i*1024u/UINT32_MAX);unsigned actual=ps_fraction(i,0,UINT32_MAX);assert(actual==reference||actual+1==reference);}
    nova_point_event e=event(0,0,0,NOVA_POINT_WORK_START,false);
    ps_event_clock(text,&e,false,true);assert(!strcmp(text,"12:00 AM"));
    e.hour=12;ps_event_clock(text,&e,false,true);assert(!strcmp(text,"12:00 PM"));
    e.hour=23;e.minute=59;e.day_offset=7;ps_event_clock(text,&e,false,true);assert(!strcmp(text,"11:59 PM +7D"));ps_event_clock(text,&e,true,true);assert(!strcmp(text,"23:59 +7D"));
    e.is_end=true;assert(!ps_event_valid(&e));e.kind=NOVA_POINT_LUNCH;assert(!strcmp(ps_event_name(&e,false),"BACK"));
    assert(WATCH_FACE_COUNT==33&&WATCH_FACE_CATEGORY_COUNT==5);
    assert(watch_face_pages[4].count==9);
    for(unsigned i=0;i<9;i++){assert(watch_face_pages[4].ids[i]==24+i);assert(watch_face_category_for(24+i)==4);}
    nova_point_event commute=event(0,5,30,NOVA_POINT_CUSTOM_1,false);
    memcpy(commute.label,"Drive to Work",14);commute.color_index=6;
    assert(ps_event_valid(&commute)&&!strcmp(ps_event_name(&commute,false),"Drive to Work"));
    nova_point_event work=event(0,6,0,NOVA_POINT_WORK_START,false);
    assert(!strcmp(ps_event_name(&work,false),"WORK"));
    nova_watch_state s;nova_points_state p;
    for(unsigned scenario=0;scenario<18;scenario++)for(unsigned face=24;face<WATCH_FACE_COUNT;face++) {
        fixture(&s,&p,scenario);guarded_render(&s,face);
        if(argc>1){char path[512];snprintf(path,sizeof(path),"%s/case-%02u-face-%u.rgb565",argv[1],scenario,face);FILE*f=fopen(path,"wb");assert(f);assert(fwrite(tight,1,sizeof(tight),f)==sizeof(tight));fclose(f);}
    }
    /* Unknown time suppresses stale schedule content as well as stale RTC. */
    for(unsigned face=24;face<WATCH_FACE_COUNT;face++) {
        fixture(&s,&p,4);guarded_render(&s,face);memcpy(compare,tight,sizeof(tight));
        s.time=(twatch_rtc_time_v1){2048,8,30,0,23,57,59};memset(&p,0xff,sizeof(p));guarded_render(&s,face);assert(!memcmp(compare,tight,sizeof(tight)));
    }
    /* All original 24 faces ignore the new projection and preserve pixels. */
    for(unsigned face=0;face<24;face++){fixture(&s,&p,0);s.points=NULL;guarded_render(&s,face);memcpy(compare,tight,sizeof(tight));s.points=&p;guarded_render(&s,face);assert(!memcmp(compare,tight,sizeof(tight)));}
    fixture(&s,&p,0);nova_watch_labels l;nova_watch_format(&s,&l);
    for(unsigned count=0;count<5;count++){p.next_count=(uint8_t)count;for(unsigned face=24;face<WATCH_FACE_COUNT;face++)guarded_render(&s,face);}
    fixture(&s,&p,0);p.next_count=255;assert(!strcmp(ps_problem(&s,&l),"SCHEDULE ERROR"));for(unsigned face=24;face<WATCH_FACE_COUNT;face++)guarded_render(&s,face);
    fixture(&s,&p,0);p.today_count=255;assert(ps_problem(&s,&l));p.today_count=7;p.today[0].hour=255;assert(ps_problem(&s,&l));
    fixture(&s,&p,0);p.previous.at_rtc=p.now_rtc+1;assert(ps_problem(&s,&l));
    fixture(&s,&p,0);p.next[0].at_rtc=p.now_rtc;assert(!ps_problem(&s,&l));guarded_render(&s,24);
    fixture(&s,&p,0);p.work_end.at_rtc=p.work_start.at_rtc;guarded_render(&s,31);memcpy(compare,tight,sizeof(tight));p.work_valid=false;guarded_render(&s,31);assert(!memcmp(compare,tight,sizeof(tight)));
    /* DST-derived input: subtraction uses absolute time, labels supplied wall
     * time. One-hour wall retreat still has a positive 30-minute countdown. */
    fixture(&s,&p,7);assert(p.next[0].hour==1&&p.next[0].minute==15&&p.next[0].at_rtc-p.now_rtc==1800);assert(ps_fraction(p.now_rtc,p.previous.at_rtc,p.next[0].at_rtc)==341);
    /* Record identity is essential: overlapping equal-kind records cannot
     * steal another record's BACK, and an unmatched end cannot invent a band. */
    fixture(&s,&p,0);p.today_count=3;p.now_rtc=p.work_end.at_rtc-60;
    p.next_count=1;p.next[0]=p.work_end;p.previous=p.work_start;
    p.today[0]=event(844473600,10,0,NOVA_POINT_BREAK,false);p.today[0].source_slot=0;
    p.today[1]=event(844473600,10,10,NOVA_POINT_BREAK,false);p.today[1].source_slot=1;
    p.today[2]=event(844473600,10,15,NOVA_POINT_BREAK,true);p.today[2].source_slot=0;
    guarded_render(&s,31);memcpy(compare,tight,sizeof(tight));
    p.today[1]=p.today[2];p.today_count=2;guarded_render(&s,31);assert(!memcmp(compare,tight,sizeof(tight)));
    p.today[1].source_slot=7;guarded_render(&s,31);assert(memcmp(compare,tight,sizeof(tight)));
    /* Malformed surfaces never touch caller bytes. */
    fixture(&s,&p,0);risc_display_surface_v1 surf={0,tight,240,240,480,sizeof(tight),5};
    surf.size_bytes--;memset(tight,0x39,sizeof(tight));assert(!nova_watch_face_render(&surf,&s,24));for(unsigned i=0;i<sizeof(tight);i++)assert(tight[i]==0x39);surf.size_bytes++;surf.stride_bytes=UINT32_MAX;assert(!nova_watch_face_render(&surf,&s,24));surf.stride_bytes=480;
    /* Copied keys must detect a projection changed in-place. */
    const watch_face_page*page=watch_face_page_for(4);face_test_calls=0;assert(nova_watch_picker_render(&surf,&s,24,-108*256,page,NULL,WATCH_FACE_COUNT,256,&cache));assert(face_test_calls==3);
    p.now_rtc++;s.time.second++;face_test_calls=0;assert(nova_watch_picker_render(&surf,&s,24,-108*256,page,NULL,WATCH_FACE_COUNT,256,&cache));assert(face_test_calls==1);
    p.revision++;face_test_calls=0;assert(nova_watch_picker_render(&surf,&s,24,-108*256,page,NULL,WATCH_FACE_COUNT,256,&cache));assert(face_test_calls==3);
    p.next[0].at_rtc++;face_test_calls=0;assert(nova_watch_picker_render(&surf,&s,24,-108*256,page,NULL,WATCH_FACE_COUNT,256,&cache));assert(face_test_calls==3);
    for(unsigned slot=0;slot<6;slot++)assert(!(cache.valid_mask&(1u<<slot))||cache.face_ids[slot]<WATCH_FACE_COUNT);
    int positions[WATCH_FACE_CATEGORY_COUNT]={0,0,0,0,-108*256};
    for(int pos=40;pos>=-1240;pos-=11){face_test_calls=0;assert(nova_watch_picker_collections_render(&surf,&s,24,pos*256,positions,NULL,WATCH_FACE_COUNT,256,&cache));assert(face_test_calls<=6);face_test_calls=0;assert(nova_watch_picker_collections_render(&surf,&s,24,pos*256,positions,NULL,WATCH_FACE_COUNT,256,&cache));assert(face_test_calls==1);}
    assert(sizeof(cache.pixels)==6*240*240*2);
    assert(nova_watch_alarm_render(&surf,false,false,false,false,false,true));memcpy(compare,tight,sizeof(tight));assert(nova_watch_alarm_label_render(&surf,NULL,false,false,false,false,false,true));assert(!memcmp(compare,tight,sizeof(tight)));
    assert(nova_watch_alarm_label_render(&surf,"WORK START",false,false,false,false,false,true));assert(memcmp(compare,tight,sizeof(tight)));
    char nonterminated[23];memset(nonterminated,'A',sizeof(nonterminated));assert(nova_watch_alarm_label_render(&surf,nonterminated,false,false,false,false,false,true));
    puts("Points renderer:18 production scenarios x9 faces; padded/tight guards; original24 unchanged; duration/day/DST/empty/error/no-pair; bounded6-slot picker with in-place invalidation; alarm labels passed");
    return 0;
}
