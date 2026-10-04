#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nova.h"
static uint8_t pixels[240*240*2];
int main(int argc,char **argv) {
    nova_watch_state state={{2026,10,3,6,10,42,18},true,true,84,250,15000};
    if (argc>1) {
        if (!strcmp(argv[1],"unset")) state.time_valid=false;
        else if (!strcmp(argv[1],"zero")) state.battery_percent=0;
        else if (!strcmp(argv[1],"unknown")) state.battery_valid=false;
        else if (!strcmp(argv[1],"midnight")) { state.time.hour=0;state.time.minute=0;state.time.second=0;state.subsecond_ms=0; }
        else if (!strcmp(argv[1],"noon")) { state.time.hour=12;state.time.minute=0;state.time.second=0;state.subsecond_ms=0; }
        else if (!strcmp(argv[1],"phase")) { assert(argc==4);state.animation_ms=(uint32_t)strtoul(argv[2],NULL,10);unsigned elapsed=(unsigned)strtoul(argv[3],NULL,10);state.subsecond_ms=(uint16_t)(elapsed%1000);state.time.second=(uint8_t)((18+elapsed/1000)%60); }
    }
    risc_display_surface_v1 surface={1,pixels,240,240,480,sizeof(pixels),RISC_DISPLAY_FORMAT_RGB565};
    assert(nova_watch_render(&surface,&state));
    assert(fwrite(pixels,1,sizeof(pixels),stdout)==sizeof(pixels));
    return 0;
}
