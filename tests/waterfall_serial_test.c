/* Real Waterfall app, copied radio diagnostics, and production Runtime logger. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "waterfall.c"

extern void waterfall_serial_start(const char *mode);
extern void waterfall_serial_line(const char *line);
extern void waterfall_serial_finish(const char *directory, const char *mode);

static t5_app_api_v1 app;
static risc_runtime_api_v1 runtime_api;
static risc_key_value_v1 kv;
static risc_radio_iq_diagnostics_api_v1 radio;
static unsigned polls, captures, copies, releases, live, lines, launches;
static bool use_back, active;
static int32_t screen(void) { return 240; }
static void clear(void) { assert(active); }
static void fill(int32_t x,int32_t y,int32_t w,int32_t h,bool black) {
    (void)black;
    assert(active && x>=0 && y>=0 && w>0 && h>0 && x+w<=240 && y+h<=240);
}
static void present(bool full) { assert(active && !full); }
static bool poll(t5_app_input_t *out,uint32_t wait) {
    assert(active && wait==30);
    memset(out,0,sizeof(*out));
    if (++polls==1) return true;
    if (use_back) { out->tapped=true;out->touch_x=10;out->touch_y=5;return true; }
    return false;
}
static int32_t get(void *context,const char *key,void *dst,uint32_t cap,uint32_t *size) {
    assert(active && context==&kv && !strcmp(key,PORTABLE_RADIO_KEY) && cap==4);
    assert(portable_radio_services_safe());
    uint8_t *b=dst;b[0]=0x51;b[1]=1;b[2]=PORTABLE_RADIO_WIFI;b[3]=b[2]^0xa5;*size=4;
    return RISC_KEY_VALUE_OK;
}
static int32_t put(void *context,const char *key,const void *value,uint32_t size) {
    (void)context;(void)key;(void)value;(void)size;assert(0);return -1;
}
static int capture(void *context,uint32_t *pairs,uint32_t count) {
    assert(active && context==&radio.base && pairs && count==RISC_RADIO_IQ_PAIRS);
    assert(portable_radio_services_safe());++captures;return RISC_RADIO_IQ_DUMP_TIMEOUT;
}
static bool suspend_radio(void *context) { assert(active && context==&radio.base);return true; }
static bool copy_diagnostics(void *context,risc_radio_iq_diagnostics_v1 *out) {
    assert(active && context==&radio.base && out && out->struct_size==sizeof(*out));
    ++copies;
    *out=(risc_radio_iq_diagnostics_v1){.struct_size=sizeof(*out),.stage=RISC_RADIO_IQ_STAGE_DUMP,
        .result=RISC_RADIO_IQ_DUMP_TIMEOUT,.requested_pairs=256,.clock_mask=64,
        .dump_before=44,.dump_after=44,.elapsed_cycles=2400010,.dump_ready=0,.cleanup_ok=1};
    return true;
}
static bool acquire(const char *name,uint32_t version,uint64_t instance,risc_runtime_capability_v1 *out) {
    assert(active && version==1 && out && out->struct_size==sizeof(*out));
    if (!strcmp(name,RISC_KEY_VALUE_CAPABILITY)) { assert(instance==1);out->api=&kv;out->slot=1; }
    else { assert(!strcmp(name,"radio.iq") && instance==0);out->api=&radio.base;out->slot=2; }
    ++live;out->generation=1;return true;
}
static bool release(risc_runtime_capability_v1 *grant) {
    assert(active && grant && live && portable_radio_services_safe());++releases;--live;return true;
}
static void yield(uint32_t ms) { (void)ms;assert(0); }
static bool launch(const char *file) {
    assert(active && !strcmp(file,"springboard.elf"));++launches;return true;
}
static bool diagnostic(const char *line) {
    assert(active && line && strlen(line)<96 && !strchr(line,'\n') && !strchr(line,'\r'));
    ++lines;waterfall_serial_line(line);return true;
}
const t5_app_api_v1 *t5_app_get_api(uint32_t version) { assert(active && version==1);return &app; }
const risc_runtime_api_v1 *risc_runtime_get_api(uint32_t version) { assert(active && version==1);return &runtime_api; }

int main(int argc,char **argv) {
    assert(argc==4);
    use_back=!strcmp(argv[3],"back");
    waterfall_serial_start(argv[2]);
    app=(t5_app_api_v1){.abi_version=1,.struct_size=sizeof(app),.screen_width=screen,
        .screen_height=screen,.clear=clear,.fill_rect=fill,.present=present,.poll=poll};
    runtime_api=(risc_runtime_api_v1){.api_version=1,.struct_size=sizeof(runtime_api),.acquire=acquire,
        .release=release,.yield_ms=yield,.request_launch=launch,.diagnostic=diagnostic};
    kv=(risc_key_value_v1){.api_version=1,.struct_size=sizeof(kv),.context=&kv,.get=get,.put=put};
    radio=(risc_radio_iq_diagnostics_api_v1){.base={.api_version=1,.struct_size=sizeof(radio),
        .context=&radio.base,.capture_burst=capture,.suspend=suspend_radio},.diagnostics=copy_diagnostics};
    active=true;app_main();active=false;
    assert(captures==1 && copies==1 && releases==2 && live==0 && lines==8);
    assert(launches==(use_back?1u:0u));
    /* Invalidate the complete fixture before replay: no app/provider pointer is
     * needed to print journal-owned copies after app_main and grant release. */
    memset(&app,0,sizeof(app));memset(&runtime_api,0,sizeof(runtime_api));
    memset(&kv,0,sizeof(kv));memset(&radio,0,sizeof(radio));
    waterfall_serial_finish(argv[1],argv[2]);
    printf("Waterfall %s/%s: capture=4 copies=1 released=2 live=0 diagnostics=8 PASS\n",argv[2],argv[3]);
    return 0;
}
