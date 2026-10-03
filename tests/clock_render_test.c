#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "apps/clock/render.h"
static uint8_t guarded[240*484+32];
static uint8_t previous[240*484];
static risc_display_surface_v1 surface={1,guarded+16,240,240,484,240*484,RISC_DISPLAY_FORMAT_RGB565};
static uint32_t checksum(void){uint32_t h=2166136261u;for(unsigned i=16;i<sizeof(guarded)-16;i++)h=(h^guarded[i])*16777619u;return h;}
int main(void){
 memset(guarded,0xa5,sizeof(guarded));
 twatch_rtc_time_v1 time={2028,2,29,2,23,59,58};
 assert(watch_clock_render(&surface,&time,true,123));uint32_t valid=checksum();
 for(unsigned i=0;i<16;i++)assert(guarded[i]==0xa5 && guarded[sizeof(guarded)-1-i]==0xa5);
 for(unsigned y=0;y<240;y++)for(unsigned x=480;x<484;x++)assert(guarded[16+y*484+x]==0xa5);
 time.second=59;assert(watch_clock_render(&surface,&time,true,123));assert(checksum()!=valid);
 assert(watch_clock_render(&surface,NULL,false,123));uint32_t unset=checksum();assert(unset!=valid);
 memcpy(previous,guarded+16,sizeof(previous));time.year=2027;
 assert(watch_clock_render(&surface,&time,true,123));assert(memcmp(previous,guarded+16,sizeof(previous))==0);
 surface.size_bytes=100;assert(!watch_clock_render(&surface,&time,true,1));assert(memcmp(previous,guarded+16,sizeof(previous))==0);
 surface.size_bytes=sizeof(previous);surface.stride_bytes=UINT32_MAX;assert(!watch_clock_render(&surface,&time,true,1));
 surface.stride_bytes=484;surface.pixel_format=RISC_DISPLAY_FORMAT_MONO1;assert(!watch_clock_render(&surface,&time,true,1));
 return 0;
}
