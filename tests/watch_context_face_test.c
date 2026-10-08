#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define WATCH_FACE_TEXT_TEST
#include "apps/clock/nova/nova.c"
static bool saw_room,saw_event,saw_unknown;
static void face_text_test(const face_font *font,const char *text,int x,int y,int spacing,int fit,const uint8_t *alpha) {
    (void)font;(void)x;(void)y;(void)spacing;(void)fit;(void)alpha;
    if(!strcmp(text,"LIVING ROOM")||!strcmp(text,"WORKSHOP"))saw_room=true;
    if(!strcmp(text,"DOOR CHIME")||!strcmp(text,"TRANSMITTER"))saw_event=true;
    if(!strcmp(text,"NO CURRENT ROOM"))saw_unknown=true;
}
static unsigned checkpoint_count,checkpoint_fail;
static bool raster_checkpoint(void *c){(void)c;checkpoint_count++;return !checkpoint_fail||checkpoint_count<checkpoint_fail;}
int main(int argc,char **argv) {
    uint8_t guarded[240*488+32];memset(guarded,0xa5,sizeof(guarded));
    risc_display_surface_v1 surface={1,guarded+16,240,240,488,240*488,RISC_DISPLAY_FORMAT_RGB565};
    nova_watch_state state={.time={2026,10,8,4,10,42,18},.time_valid=true,.battery_valid=true,.battery_percent=84};
    for(unsigned scenario=0;scenario<8;scenario++) {
        state.contexts=(nova_context_state){0};
        if(scenario){state.contexts.enabled=true;state.contexts.ready=scenario>1;state.contexts.paused=scenario==2;}
        if(scenario>=3) {
            strcpy(state.contexts.room,scenario==4?"Workshop":"Living room");
            strcpy(state.contexts.event,scenario==4?"Transmitter":"Door chime");
            state.contexts.source=scenario==4?2:1;state.contexts.room_valid=state.contexts.event_valid=true;
        }
        if(scenario==5){state.contexts.ambiguous=true;state.contexts.event_valid=false;}
        if(scenario==6){memset(state.contexts.room,'X',17);memset(state.contexts.event,'X',17);}
        if(scenario==7)state.contexts.paused=true;
        saw_room=saw_event=saw_unknown=false;assert(nova_watch_face_render(&surface,&state,33));
        assert(saw_room==(scenario==3||scenario==4));assert(saw_event==(scenario==3||scenario==4));
        assert(saw_unknown==(scenario!=3&&scenario!=4));
        for(unsigned i=0;i<16;i++)assert(guarded[i]==0xa5&&guarded[sizeof(guarded)-1-i]==0xa5);
        for(unsigned y=0;y<240;y++)for(unsigned x=480;x<488;x++)assert(guarded[16+y*488+x]==0xa5);
        if(argc>1){char path[512];snprintf(path,sizeof(path),"%s/context-%u.rgb565",argv[1],scenario);FILE*f=fopen(path,"wb");assert(f);for(unsigned y=0;y<240;y++)assert(fwrite(guarded+16+y*488,1,480,f)==480);assert(!fclose(f));}
    }
    /* Every production face services long raster work and stops after a failed
     * owner callback. Padding/guards are unchanged, including after failure. */
    state.capture_audio=raster_checkpoint;
    for(unsigned id=0;id<WATCH_FACE_COUNT;id++) {
        checkpoint_count=checkpoint_fail=0;assert(nova_watch_face_render(&surface,&state,id));assert(checkpoint_count>30);
        checkpoint_count=0;checkpoint_fail=35;assert(!nova_watch_face_render(&surface,&state,id));assert(checkpoint_count==35);
        for(unsigned i=0;i<16;i++)assert(guarded[i]==0xa5&&guarded[sizeof(guarded)-1-i]==0xa5);
        for(unsigned y=0;y<240;y++)for(unsigned x=480;x<488;x++)assert(guarded[16+y*488+x]==0xa5);
    }
    checkpoint_count=0;checkpoint_fail=35;assert(!nova_watch_render(&surface,&state)&&checkpoint_count==35);
    surface.size_bytes--;assert(!nova_watch_face_render(&surface,&state,33));
    assert(!strcmp(nova_watch_face_name(33),"CONTEXTS"));
    puts("Context face: off/loading/paused/audio/RF/ambiguous/malformed/stale, exact text and guarded pixels PASS");return 0;
}
