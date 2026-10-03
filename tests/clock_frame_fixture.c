#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "apps/clock/nova/nova.h"
static uint8_t pixels[240*240*2];
int main(int argc,char **argv){
 assert(argc==2);
 bool valid=!strcmp(argv[1],"valid");assert(valid||!strcmp(argv[1],"unset"));
 risc_display_surface_v1 surface={1,pixels,240,240,480,sizeof(pixels),RISC_DISPLAY_FORMAT_RGB565};
 twatch_rtc_time_v1 time={2028,2,29,2,12,34,0};
 nova_watch_state state={.time=time,.time_valid=valid,.battery_valid=false,.animation_ms=18250,.subsecond_ms=250};
 assert(nova_watch_render(&surface,&state));
 assert(fwrite(pixels,1,sizeof(pixels),stdout)==sizeof(pixels));
 return 0;
}
