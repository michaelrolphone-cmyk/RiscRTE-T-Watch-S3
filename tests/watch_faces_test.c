#include "apps/clock/nova/nova.h"
#include "apps/clock/faces/picker.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned puts_count;static uint8_t stored[4];static int failure;static bool exists;
static int32_t get(void*c,const char*k,void*b,uint32_t n,uint32_t*z){(void)c;assert(!strcmp(k,WATCH_FACE_KEY));*z=0;if(failure==2)return -5;if(!exists)return -1;assert(n==4);memcpy(b,stored,4);*z=4;return 0;}
static int32_t putv(void*c,const char*k,const void*b,uint32_t n){(void)c;assert(!strcmp(k,WATCH_FACE_KEY)&&n==4);puts_count++;if(failure==1)return -5;memcpy(stored,b,4);exists=true;return 0;}
int main(int argc,char**argv) {
    risc_key_value_v1 kv={1,sizeof(kv),NULL,get,putv};unsigned v;
    assert(watch_face_load(&kv,&v)==-1&&v==0);
    for(unsigned i=0;i<WATCH_FACE_COUNT;i++){assert(watch_face_save(&kv,i));assert(watch_face_load(&kv,&v)==0&&v==i);unsigned n=puts_count;assert(watch_face_save(&kv,i)&&puts_count==n);}
    stored[2]=WATCH_FACE_COUNT;assert(watch_face_load(&kv,&v)==-3&&v==0);assert(!watch_face_save(&kv,WATCH_FACE_COUNT));failure=1;assert(!watch_face_save(&kv,4));failure=2;assert(!watch_face_save(&kv,4));failure=0;
    watch_face_picker p={0};assert(!watch_face_input(&p,0,true,1,1,120,120));assert(!p.down);
    watch_face_input(&p,1,true,0,0,0,0);watch_face_input(&p,10,true,1,1,120,120);
    assert(watch_face_input(&p,609,true,1,1,120,120)==0);
    assert(watch_face_input(&p,610,true,1,1,120,120)==WATCH_FACE_OPEN&&p.open);
    assert(watch_face_input(&p,620,true,1,1,50,120)==0&&p.position==0);
    assert(watch_face_input(&p,630,true,0,0,0,0)==0); /* opening release cannot select */
    watch_face_input(&p,640,true,1,2,120,92);assert(watch_face_input(&p,650,true,0,0,0,0)==WATCH_FACE_SELECT&&p.target==0);
    watch_face_input(&p,660,true,1,3,120,92);watch_face_input(&p,700,true,1,3,12,92);assert(watch_face_input(&p,710,true,0,0,0,0)==0);
    for(unsigned t=720;t<5000;t+=20)watch_face_animate(&p,t);
    assert(watch_face_nearest(&p)>0);
    watch_face_close(&p);watch_face_input(&p,5100,true,0,0,0,0);watch_face_input(&p,5200,true,1,1,120,120);
    watch_face_input(&p,5300,true,1,1,129,120);watch_face_input(&p,5400,true,1,1,120,120);assert(watch_face_input(&p,5900,true,1,1,120,120)==0&&!p.open);
    assert(watch_face_input(&p,5910,true,1,1,140,120)==WATCH_FACE_LAUNCHER);
    watch_face_input(&p,6000,true,0,0,0,0);watch_face_input(&p,6010,true,1,1,120,120);watch_face_input(&p,6100,true,2,1,120,120);assert(watch_face_input(&p,7000,true,1,1,120,120)==0&&!p.open);
    watch_face_input(&p,7010,true,0,0,0,0);watch_face_input(&p,7020,true,1,1,120,120);watch_face_input(&p,7030,true,1,2,120,120);assert(watch_face_input(&p,8000,true,1,2,120,120)==0&&!p.open);
    watch_face_input(&p,8010,true,0,0,0,0);watch_face_input(&p,0xffffff00u,true,1,3,120,120);assert(watch_face_input(&p,344,true,1,3,120,120)==WATCH_FACE_OPEN);
    /* Exact source-equation trajectory, independent of presentation cadence. */
    for(unsigned edge=0;edge<2;edge++) {
        watch_face_picker expected={.open=true,.category=1,.position=edge?-7*WATCH_FACE_PITCH-20*256:20*256,.velocity=edge?-6*256:6*256};
        for(unsigned t=1;t<=2000;t++)watch_face_animate(&expected,t);
        const unsigned intervals[]={8,20,50,95};
        for(unsigned n=0;n<4;n++) {
            watch_face_picker q={.open=true,.category=1,.position=edge?-7*WATCH_FACE_PITCH-20*256:20*256,.velocity=edge?-6*256:6*256};
            unsigned t=0;while(t<2000){t+=intervals[n];if(t>2000)t=2000;watch_face_animate(&q,t);}
            assert(q.position==expected.position&&q.velocity==expected.velocity&&q.target==expected.target&&q.phase==expected.phase);
        }
    }
    watch_face_picker resistance={.open=true,.neutral=true,.position=24*256};
    watch_face_input(&resistance,0,true,1,1,100,92);watch_face_input(&resistance,8,true,1,1,124,92);
    assert(resistance.position==36*256); /*24px drag / (1 +24/24)*/
    uint8_t pixels[240*488+32];nova_watch_picker_cache scratch={0};memset(pixels,0xa5,sizeof(pixels));
    risc_display_surface_v1 s={0,pixels+16,240,240,488,240*488,5};
    nova_watch_state state={.time={.year=2026,.month=10,.day=4,.weekday=0,.hour=10,.minute=42,.second=18},.time_valid=true,.battery_valid=true,.battery_percent=84,.subsecond_ms=250,.animation_ms=42000};
    for(unsigned i=0;i<WATCH_FACE_COUNT;i++) {
        assert(nova_watch_face_render(&s,&state,i));
        for(unsigned n=0;n<16;n++)assert(pixels[n]==0xa5&&pixels[sizeof(pixels)-n-1]==0xa5);
        for(unsigned y=0;y<240;y++)for(unsigned n=480;n<488;n++)assert(pixels[16+y*488+n]==0xa5);
        if(argc>1){char path[512];snprintf(path,sizeof(path),"%s/face-%u.rgb565",argv[1],i);FILE*f=fopen(path,"wb");assert(f);for(unsigned y=0;y<240;y++)assert(fwrite(pixels+16+y*488,1,480,f)==480);fclose(f);}
        unsigned category=watch_face_category_for(i),index=watch_face_index_for(category,i);
        assert(nova_watch_picker_render(&s,&state,i,-(int)index*WATCH_FACE_PITCH,watch_face_page_for(category),NULL,WATCH_FACE_COUNT,256,&scratch));
        if(argc>1){char path[512];snprintf(path,sizeof(path),"%s/picker-%u.rgb565",argv[1],i);FILE*f=fopen(path,"wb");assert(f);for(unsigned y=0;y<240;y++)assert(fwrite(pixels+16+y*488,1,480,f)==480);fclose(f);}
        state.time_valid=false;state.battery_valid=false;assert(nova_watch_face_render(&s,&state,i));state.time_valid=true;state.battery_valid=true;
    }
    assert(nova_watch_picker_pulse(0)==256&&nova_watch_picker_pulse(167)==276&&nova_watch_picker_pulse(334)==256&&nova_watch_picker_pulse(UINT32_MAX)==256);
    state.time.second=5;assert(nova_watch_face_render(&s,&state,2));
    unsigned blip=(85*488+140*2);uint16_t recent=pixels[16+blip]|pixels[17+blip]<<8;
    state.time.second=35;assert(nova_watch_face_render(&s,&state,2));uint16_t old=pixels[16+blip]|pixels[17+blip]<<8;
    assert(((recent>>5)&63)>((old>>5)&63));
    s.size_bytes--;assert(!nova_watch_face_render(&s,&state,0));
    puts("24 native faces: guarded stride/invalid telemetry; gestures: hold/swipe/jitter/drag/gaps/id/rollover; persistence: all IDs, corruption and failed read/write passed");
}
