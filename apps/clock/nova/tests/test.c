#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "nova.h"
static uint8_t guarded[240*484+32], saved[240*484], tight[240*480];
static risc_display_surface_v1 frame={1,guarded+16,240,240,484,240*484,RISC_DISPLAY_FORMAT_RGB565};
static nova_watch_state input={{2026,10,3,6,10,42,18},true,true,84,250,15000,false};
static unsigned assertions;
#define CHECK(x) do { assert(x);assertions++; } while (0)
static uint32_t hash_region(int lo,int hi) {
    uint32_t h=2166136261u;
    for (int y=0;y<240;y++) for (int x=0;x<240;x++) {
        int r=(x-120)*(x-120)+(y-120)*(y-120);
        if (r>=lo*lo && r<=hi*hi) for (unsigned b=0;b<2;b++) h=(h^guarded[16+y*484+x*2+b])*16777619u;
    }
    return h;
}
static uint32_t hash_rect(unsigned x0,unsigned y0,unsigned x1,unsigned y1) {
    uint32_t h=2166136261u;
    for(unsigned y=y0;y<y1;y++) for(unsigned x=x0;x<x1;x++) for(unsigned b=0;b<2;b++)
        h=(h^guarded[16+y*484+x*2+b])*16777619u;
    return h;
}
static uint16_t pixel(unsigned x,unsigned y) { uint8_t *p=guarded+16+y*484+x*2;return p[0]|((uint16_t)p[1]<<8); }
static void render(void) { CHECK(nova_watch_render(&frame,&input)); }
static void guards(void) {
    for (unsigned i=0;i<16;i++) CHECK(guarded[i]==0xa5 && guarded[sizeof(guarded)-1-i]==0xa5);
    for (unsigned y=0;y<240;y++) for (unsigned x=480;x<484;x++) CHECK(guarded[16+y*484+x]==0xa5);
}
int main(void) {
    nova_watch_labels label; memset(guarded,0xa5,sizeof(guarded));render();guards();
    nova_watch_format(&input,&label);CHECK(!strcmp(label.hour_minute,"10:42"));
    CHECK(!strcmp(label.meridiem,"AM"));CHECK(!strcmp(label.date,"SAT 03 OCT"));CHECK(!strcmp(label.status,"RTC"));
    CHECK(!strcmp(label.battery,"84%"));
    /* Explicit midnight/noon and 11:59:59 -> 12:00 transitions. */
    const unsigned hours[]={0,1,11,12,13,23};const char *hm[]={"12:42","01:42","11:42","12:42","01:42","11:42"};
    for (unsigned i=0;i<6;i++) { input.time.hour=hours[i];nova_watch_format(&input,&label);CHECK(!strcmp(label.hour_minute,hm[i]));CHECK(!strcmp(label.meridiem,hours[i]<12?"AM":"PM")); }
    input.time=(twatch_rtc_time_v1){2028,2,29,2,23,59,59};nova_watch_format(&input,&label);
    CHECK(label.time_valid);CHECK(!strcmp(label.date,"TUE 29 FEB"));CHECK(!strcmp(label.hour_minute,"11:59"));CHECK(!strcmp(label.meridiem,"PM"));
    input.time=(twatch_rtc_time_v1){2028,3,1,3,0,0,0};nova_watch_format(&input,&label);
    CHECK(!strcmp(label.hour_minute,"12:00"));CHECK(!strcmp(label.meridiem,"AM"));CHECK(!strcmp(label.date,"WED 01 MAR"));
    input.time.hour=12;nova_watch_format(&input,&label);CHECK(!strcmp(label.hour_minute,"12:00"));CHECK(!strcmp(label.meridiem,"PM"));
    input.time=(twatch_rtc_time_v1){2027,2,29,1,10,42,18};nova_watch_format(&input,&label);
    CHECK(!label.time_valid);CHECK(!strcmp(label.hour_minute,"--:--"));CHECK(!strcmp(label.status,"UNSET"));CHECK(!strcmp(label.meridiem,"--"));render();
    memcpy(saved,guarded+16,sizeof(saved));input.time_valid=false;render();CHECK(!memcmp(saved,guarded+16,sizeof(saved)));
    input.time_valid=true;input.time=(twatch_rtc_time_v1){2026,10,3,6,10,42,18};
    /* Real zero is empty, unavailable/out-of-range is visibly unknown. */
    input.battery_percent=0;render();nova_watch_format(&input,&label);CHECK(label.battery_valid);CHECK(!strcmp(label.battery,"0%"));CHECK(pixel(110,190)!=0x3ff3);
    memcpy(saved,guarded+16,sizeof(saved));input.battery_valid=false;render();nova_watch_format(&input,&label);CHECK(!label.battery_valid);CHECK(!strcmp(label.battery,"--%"));CHECK(memcmp(saved,guarded+16,sizeof(saved)));
    memcpy(saved,guarded+16,sizeof(saved));input.battery_valid=true;input.battery_percent=101;render();CHECK(!memcmp(saved,guarded+16,sizeof(saved)));
    input.battery_percent=100;render();nova_watch_format(&input,&label);CHECK(!strcmp(label.battery,"100%"));CHECK(pixel(133,190)==0x3ff3);
    /* Annular hashes isolate each animation from the other ring and labels. */
    input.time_valid=false;input.animation_ms=0;render();uint32_t ring82=hash_region(81,83),ring76=hash_region(75,77);
    input.animation_ms=90000;render();CHECK(hash_region(81,83)==ring82);
    input.animation_ms=40000;render();CHECK(hash_region(75,77)==ring76);
    input.animation_ms=15000;render();CHECK(hash_region(81,83)!=ring82);CHECK(hash_region(75,77)!=ring76);
    /* Fractional seconds and colon phases visibly change; minute wraps arc. */
    input.time_valid=true;input.time.second=59;input.subsecond_ms=999;render();uint32_t full=hash_region(94,102);
    input.time.second=0;input.subsecond_ms=0;render();CHECK(full!=hash_region(94,102));uint32_t start=hash_region(94,102);
    input.subsecond_ms=250;render();CHECK(start!=hash_region(94,102));
    input.subsecond_ms=499;render();uint32_t colon=hash_rect(100,90,140,130);
    input.subsecond_ms=500;render();CHECK(colon!=hash_rect(100,90,140,130));
    input.subsecond_ms=999;render();memcpy(saved,guarded+16,sizeof(saved));input.subsecond_ms=65535;render();CHECK(!memcmp(saved,guarded+16,sizeof(saved)));
    /* Identical active pixels for tight and padded strides. */
    risc_display_surface_v1 contiguous={1,tight,240,240,480,sizeof(tight),RISC_DISPLAY_FORMAT_RGB565};
    CHECK(nova_watch_render(&contiguous,&input));for(unsigned y=0;y<240;y++) CHECK(!memcmp(tight+y*480,guarded+16+y*484,480));guards();
    /* Reject every malformed surface before any write, including overflow. */
    memcpy(saved,guarded+16,sizeof(saved));risc_display_surface_v1 bad=frame;
    bad.size_bytes--;CHECK(!nova_watch_render(&bad,&input));bad=frame;bad.stride_bytes=UINT32_MAX;CHECK(!nova_watch_render(&bad,&input));
    bad=frame;bad.stride_bytes=479;CHECK(!nova_watch_render(&bad,&input));bad=frame;bad.width=239;CHECK(!nova_watch_render(&bad,&input));
    bad=frame;bad.height=241;CHECK(!nova_watch_render(&bad,&input));bad=frame;bad.pixel_format=RISC_DISPLAY_FORMAT_MONO1;CHECK(!nova_watch_render(&bad,&input));
    bad=frame;bad.pixels=NULL;CHECK(!nova_watch_render(&bad,&input));CHECK(!nova_watch_render(NULL,&input));CHECK(!memcmp(saved,guarded+16,sizeof(saved)));
    CHECK(nova_watch_render(&frame,NULL));nova_watch_format(NULL,&label);CHECK(!label.time_valid && !label.battery_valid);guards();
    input.animation_ms=UINT32_MAX;input.subsecond_ms=65535;input.battery_percent=255;render();guards();
    /* Host-only CPU cost, not physical watch FPS or panel throughput. */
    input.time_valid=true;input.subsecond_ms=250;
    clock_t begin=clock();unsigned frames=2000;
    for(unsigned i=0;i<frames;i++) { input.animation_ms=i*50;input.subsecond_ms=i%1000;assert(nova_watch_render(&contiguous,&input)); }
    double ms=(double)(clock()-begin)*1000/CLOCKS_PER_SEC/frames;
    printf("NOVA: %u checks passed; %u host frames: %.3f ms/frame CPU (not hardware FPS)\n",assertions,frames,ms);
    return 0;
}
