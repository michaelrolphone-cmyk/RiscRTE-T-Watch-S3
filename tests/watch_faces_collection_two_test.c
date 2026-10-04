/* Production collection-two renderer exercised independently of picker state. */
#include "apps/clock/nova/nova.c"
#ifndef WATCH_COLLECTION_TWO_RENDER_INCLUDED
#include "apps/clock/faces/collection_two.inc"
#endif
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
static uint8_t pixels[240*488+32];
static void render(nova_watch_state*s,unsigned id) {
    memset(pixels,0xa5,sizeof(pixels));canvas c={pixels+16,488};
    for(unsigned y=0;y<240;y++)memset(at(&c,0,y),0,480);
    nova_watch_labels l;nova_watch_format(s,&l);
    unsigned sub=s->subsecond_ms<1000?s->subsecond_ms:999;
    int sec=l.time_valid?(int)(s->time.second*1000+sub)*1536/1000:0;
    int min=l.time_valid?(int)s->time.minute*1536+sec/60:0;
    int hour=l.time_valid?(int)(s->time.hour%12)*7680+min/12:0;
    fcollection_two(&c,s,&l,id,sec,min,hour,sub);
    for(unsigned i=0;i<16;i++)assert(pixels[i]==0xa5&&pixels[sizeof(pixels)-i-1]==0xa5);
    for(unsigned y=0;y<240;y++)for(unsigned x=480;x<488;x++)assert(pixels[16+y*488+x]==0xa5);
}
void render_collection_two_sample(void*destination,unsigned id,unsigned ms) {
    nova_watch_state s={.time={2026,10,4,0,10,42,(uint8_t)(ms/1000%60)},.time_valid=true,.battery_valid=true,.battery_percent=84,.subsecond_ms=(uint16_t)(ms%1000),.animation_ms=42000+ms};
    render(&s,id);for(unsigned y=0;y<240;y++)memcpy((uint8_t*)destination+y*480,pixels+16+y*488,480);
}
int main(int argc,char**argv) {
    nova_watch_state s={.time={2026,10,4,0,10,42,18},.time_valid=true,.battery_valid=true,.battery_percent=84,.subsecond_ms=250,.animation_ms=42000};
    assert(f2days(&(twatch_rtc_time_v1){2000,1,1,0,0,0,0})==0);
    assert(f2days(&(twatch_rtc_time_v1){2000,3,1,0,0,0,0})==60);
    assert(f2days(&(twatch_rtc_time_v1){2001,3,1,0,0,0,0})==425);
    assert(f2moon_phase(&(twatch_rtc_time_v1){2000,1,6,0,14,24,0},0)==0);
    assert(f2moon_phase(&(twatch_rtc_time_v1){2000,1,21,0,8,46,1},0)>180*256-2&&f2moon_phase(&(twatch_rtc_time_v1){2000,1,21,0,8,46,1},0)<180*256+2);
    assert(f2moon_phase(&s.time,s.subsecond_ms)>270*256-15*256&&f2moon_phase(&s.time,s.subsecond_ms)<270*256+15*256);
    for(unsigned id=0;id<8;id++) {
        render(&s,id);
        if(argc>1){char path[512];snprintf(path,sizeof(path),"%s/face-%u.rgb565",argv[1],id);FILE*f=fopen(path,"wb");assert(f);for(unsigned y=0;y<240;y++)assert(fwrite(pixels+16+y*488,1,480,f)==480);fclose(f);}
        s.time_valid=false;s.battery_valid=false;render(&s,id);s.time_valid=true;s.battery_valid=true;
        s.subsecond_ms=65535;s.animation_ms=UINT32_MAX;render(&s,id);s.subsecond_ms=250;s.animation_ms=42000;
    }
    /* Changes have no hidden global cache: repeat the same state exactly. */
    uint8_t previous[240*488+32];
    for(unsigned id=0;id<8;id++) {
        render(&s,id);memcpy(previous,pixels,sizeof(pixels));
        s.subsecond_ms=800;s.animation_ms=52000;s.time.second=28;render(&s,id);
        if(id==0||id==2||id==3||id==4||id==5||id==6||id==7)assert(memcmp(previous,pixels,sizeof(pixels)));
        s.subsecond_ms=250;s.animation_ms=42000;s.time.second=18;render(&s,id);assert(!memcmp(previous,pixels,sizeof(pixels)));
    }
    /* Every allowed RTC year and phase direction, including leap-year edges. */
    for(unsigned year=2000;year<=2099;year++){s.time.year=(uint16_t)year;s.time.month=12;s.time.day=31;assert(f2moon_phase(&s.time,999)<360*256);render(&s,0);render(&s,3);}
    for(unsigned m=0;m<=100;m+=25){s.battery_percent=(uint8_t)m;for(unsigned id=0;id<8;id++)render(&s,id);}
    s.battery_percent=255;s.time.month=0;for(unsigned id=0;id<8;id++)render(&s,id);
    if(argc>2) {
        s=(nova_watch_state){.time={2026,10,4,0,10,42,18},.time_valid=true,.battery_valid=true,.battery_percent=84,.subsecond_ms=250,.animation_ms=42000};
        for(unsigned id=0;id<8;id++){clock_t start=clock();for(unsigned i=0;i<100;i++)render(&s,id);printf("Face%u:%.3fms host CPU/frame\n",id,(double)(clock()-start)*1000/CLOCKS_PER_SEC/100);}
    }
    puts("Collection II:8faces, RTC2000..2099, moon epoch/full-phase, unknown telemetry, animation wrap, battery range and stride guards passed");
}
