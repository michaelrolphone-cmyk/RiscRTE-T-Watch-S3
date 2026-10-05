/* Real Clock load/projection from persisted bytes. No synthesized Clock state. */
#include <assert.h>
#include <stdio.h>
#define WATCH_CLOCK_LAUNCHER 1
#define WATCH_CLOCK_ALARMS 1
#define WATCH_CLOCK_POINTS 1
#include "apps/clock/crown.c"
static const char *directory;
static unsigned reads, releases, format;
static int32_t get(void *context,const char *key,void *buffer,uint32_t capacity,uint32_t *size) {
    if(context==(void*)1) {
        assert(!strcmp(key,PORTABLE_TIME_FORMAT_KEY)&&capacity==4);
        uint8_t bytes[]={0x54,1,(uint8_t)format,(uint8_t)(format^0xa5)};
        memcpy(buffer,bytes,4);*size=4;return RISC_KEY_VALUE_OK;
    }
    assert(context==(void*)5);assert(capacity==64);*size=0;reads++;
    char path[1024];snprintf(path,sizeof(path),"%s/%s",directory,key);
    FILE *f=fopen(path,"rb");if(!f)return RISC_KEY_VALUE_NOT_FOUND;
    *size=(uint32_t)fread(buffer,1,capacity,f);assert(!ferror(f));fclose(f);return RISC_KEY_VALUE_OK;
}
static const risc_key_value_v1 kv={1,sizeof(kv),(void*)5,get,NULL};
static const risc_key_value_v1 preference_kv={1,sizeof(preference_kv),(void*)1,get,NULL};
static bool acquire(const char *cap,uint32_t version,uint64_t instance,risc_runtime_capability_v1 *grant) {
    assert(!strcmp(cap,RISC_KEY_VALUE_CAPABILITY)&&version==1&&(instance==5||instance==1));grant->api=instance==5?&kv:&preference_kv;return true;
}
static bool release(risc_runtime_capability_v1 *grant){assert(grant->api==&kv||grant->api==&preference_kv);releases++;return true;}
static bool diagnostic(const char *s){puts(s);return true;}
static const risc_runtime_api_v1 runtime={.api_version=1,.struct_size=sizeof(runtime),.acquire=acquire,.release=release,.diagnostic=diagnostic};
int main(int argc,char **argv) {
    assert(argc==3);directory=argv[1];bool expected=!strcmp(argv[2],"ready");rt=&runtime;
    assert(clock_points_load());assert(releases==1&&reads>=1);
    assert(clock_points_available==expected);
    if(!expected){assert(clock_points_view.status==NOVA_POINTS_ERROR);puts("Actual Clock load: SCHEDULE ERROR reproduced from persisted config");return 0;}
    for(format=0;format<=1;format++){assert(reload_time_format());assert(face.hour_24==(format==1));}
    uint32_t now;assert(alarm_calendar_seconds(2026,10,5,2,0,0,&now));
    assert(watch_points_projection(&clock_points_config,&clock_points_meta,now,&clock_points_view));
    assert(clock_points_view.status==NOVA_POINTS_READY&&clock_points_view.next_count);
#if WATCH_POINTS_EXTENDED
    if(clock_points_config.points[0].kind==POINTS_CUSTOM_1) {
        assert(clock_points_config.points[0].notify_end&&clock_points_config.points[0].warn3);
        assert(!strcmp(clock_points_view.next[0].label,"STUDY")&&clock_points_view.next[0].color_index==3);
        assert(!clock_points_view.next[0].is_end&&clock_points_view.next[1].is_end);
        assert(clock_points_view.next[1].at_rtc-clock_points_view.next[0].at_rtc==1800);
    }
#endif
    puts("Actual Clock load: saved record READY, original start/end projection preserved");
}
