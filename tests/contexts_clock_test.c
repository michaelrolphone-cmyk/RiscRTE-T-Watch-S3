/* The actual crown implementation and existing display/touch fixtures. */
#ifndef WATCH_CONTEXTS_CLIENT
#define WATCH_CONTEXTS_CLIENT
#endif
#define WATCH_CLOCK_ALARMS
#define WATCH_QUICK_RADIOS
#define PORTABLE_LOW_BATTERY
#define main original_quick_fixture_main
#include "quick_clock_test.c"
#undef main
static contexts_status_v1 ctx_view={.struct_size=sizeof(ctx_view)};
static unsigned ctx_calls,ctx_steps,ctx_pauses,ctx_requests,ctx_begins,ctx_finishes;
static bool ctx_capturing,ctx_pause_ok=true,ctx_launch_ok=true,ctx_enabled=true;
static char ctx_launched[32];
static bool ctx_pause(void*c){(void)c;ctx_calls++;ctx_pauses++;assert(!held&&!pending);if(!ctx_pause_ok)return false;ctx_capturing=false;ctx_view.state=CONTEXTS_PAUSED;ctx_view.audio.current=ctx_view.radio.current=false;return true;}
static bool ctx_step(void*c,const contexts_policy_v1*p){(void)c;ctx_calls++;ctx_steps++;assert(!held&&!pending);ctx_capturing=p->enabled&&p->audio_allowed;ctx_view.state=ctx_capturing?CONTEXTS_LIVE:CONTEXTS_OFF;return true;}
static bool ctx_status(void*c,contexts_status_v1*out){(void)c;ctx_calls++;*out=ctx_view;return true;}
static bool ctx_request(void*c,uint32_t sources){(void)c;ctx_calls++;ctx_requests++;ctx_view.export_pending|=sources;return true;}
static bool ctx_begin(void*c,uint32_t source){(void)c;ctx_calls++;ctx_begins++;assert(ctx_view.export_pending&source);assert(!ctx_view.export_active&&!ctx_capturing);ctx_view.export_active=source;return true;}
static bool ctx_export(void*c,uint32_t s,uint32_t k,uint32_t i,const void*b,uint32_t n){(void)c;(void)s;(void)k;(void)i;(void)b;(void)n;assert(!"owner helper tested separately");return false;}
static bool ctx_finish(void*c,uint32_t source,uint32_t result){(void)c;ctx_calls++;ctx_finishes++;assert(ctx_view.export_pending&source);ctx_view.export_pending&=~source;ctx_view.export_active=0;(source==1?&ctx_view.audio:&ctx_view.radio)->model_state=result?CONTEXTS_MODEL_FAILED:CONTEXTS_MODEL_READY;return true;}
static int32_t ctx_label(void*c,uint32_t s,uint32_t i,contexts_label_v1*out){(void)c;(void)s;(void)i;(void)out;return 0;}
static bool ctx_claim(void*c,uint32_t s,uint32_t i,const char*n,uint32_t g){(void)c;(void)s;(void)i;(void)n;(void)g;return false;}
static bool ctx_result(void*c,uint32_t s,uint32_t g,uint32_t r){(void)c;(void)s;(void)g;(void)r;return true;}
static unsigned ctx_captures,ctx_capture_last,ctx_capture_gap,ctx_retains;
static bool ctx_capture_ok=true,ctx_refuse_pending;
static bool ctx_capture(void*c){(void)c;ctx_captures++;unsigned gap=clock_ms-ctx_capture_last;if(gap>ctx_capture_gap)ctx_capture_gap=gap;ctx_capture_last=clock_ms;return ctx_capture_ok&&!(ctx_refuse_pending&&pending);}
static bool ctx_retain(void){ctx_retains++;return true;}
static const contexts_service_v1 ctx_api={.api_version=1,.struct_size=sizeof(ctx_api),.step=ctx_step,.pause=ctx_pause,.status=ctx_status,.request_export=ctx_request,.begin_export=ctx_begin,.export_record=ctx_export,.finish_export=ctx_finish,.label=ctx_label,.claim_preset=ctx_claim,.preset_result=ctx_result,.capture_audio=ctx_capture};
static int32_t ctx_get(void*c,const char*k,void*b,uint32_t n,uint32_t*z){
    if(!strcmp(k,PORTABLE_CONTEXT_ENABLED_KEY)){assert(n>=4);uint8_t bytes[]={'C',1,ctx_enabled?1:0,(uint8_t)((ctx_enabled?1:0)^0xa5)};memcpy(b,bytes,4);*z=4;return 0;}
    return face_get(c,k,b,n,z);
}
static const risc_key_value_v1 ctx_kv={1,sizeof(ctx_kv),NULL,ctx_get,face_put};
static alarm_status_v1 ctx_alarm={.api_version=1,.struct_size=sizeof(ctx_alarm),.state=ALARM_STATE_READY};
static bool inject_alarm;
static int32_t ctx_alarm_status(void*c,alarm_status_v1*out){(void)c;*out=ctx_alarm;return 0;}
static int32_t ctx_alarm_step(void*c){(void)c;if(ctx_alarm.state==ALARM_STATE_ALERT)assert(!ctx_capturing);if(inject_alarm){ctx_alarm.state=ALARM_STATE_ALERT;ctx_alarm.occurrence.generation=1;inject_alarm=false;}return 0;}
static int32_t ctx_alarm_refresh(void*c){(void)c;return 0;}
static int32_t ctx_alarm_ack(void*c,const alarm_token_v1*t){(void)c;(void)t;ctx_alarm.state=ALARM_STATE_READY;ctx_alarm.occurrence.generation=0;return 0;}
static int32_t ctx_alarm_prepare(void*c,alarm_sleep_v1*out){(void)c;*out=(alarm_sleep_v1){.struct_size=sizeof(*out)};return 0;}
static const alarm_service_v1 ctx_alarm_api={1,sizeof(ctx_alarm_api),NULL,ctx_alarm_status,ctx_alarm_step,ctx_alarm_refresh,ctx_alarm_ack,ctx_alarm_prepare,ctx_alarm_refresh};
static bool ctx_acquire(const char*n,uint32_t version,uint64_t instance,risc_runtime_capability_v1*g) {
    if(!strcmp(n,CONTEXTS_SERVICE_CAPABILITY)){assert(version==1&&!instance);g->api=&ctx_api;grants++;return true;}
    if(!strcmp(n,ALARM_SERVICE_CAPABILITY)){assert(version==1&&!instance);g->api=&ctx_alarm_api;grants++;return true;}
    if(!strcmp(n,RISC_KEY_VALUE_CAPABILITY)){assert(version==1&&instance==1);g->api=&ctx_kv;grants++;return true;}
    return acquire_cap(n,version,instance,g);
}
static bool ctx_launch(const char*path){assert(!held&&!pending&&!ctx_capturing);assert(!strcmp(path,"audio_spectrum.elf")||!strcmp(path,"waterfall.elf"));strcpy(ctx_launched,path);return ctx_launch_ok;}
static const struct {risc_runtime_api_v1 prefix;bool(*confirm)(void);bool(*retain)(void);} ctx_runtime_extended={{1,sizeof(ctx_runtime_extended),health,yield,diagnostic,ctx_launch,ctx_acquire,release_cap},NULL,ctx_retain};
#define ctx_runtime ctx_runtime_extended.prefix
int main(void) {
    scenario=30;rt=&ctx_runtime;clock_display_settled=true;display=&da.base;pmu=&pa;rtc=&ra;panel=&da;submitted=last_complete=1;
    pqa_session_init(&clock_quick);clock_quick.ui.neutral_gate=false;clock_alarm.api=&ctx_alarm_api;
    assert(portable_contexts_open(&clock_contexts,rt));
    assert(clock_contexts_tick()&&clock_contexts_handoff&&!strcmp(ctx_launched,"audio_spectrum.elf"));
    assert(ctx_requests==1&&ctx_begins==1&&ctx_view.export_active==1&&ctx_view.export_pending==3);
    /* An abandoned owner does not loop; recovery records failure once. */
    clock_contexts_handoff=false;assert(clock_contexts_recover_export());assert(ctx_finishes==1&&ctx_view.audio.model_state==CONTEXTS_MODEL_FAILED);
    assert(clock_contexts_tick()&&clock_contexts_handoff&&!strcmp(ctx_launched,"waterfall.elf"));
    assert(ctx_finish(NULL,2,0));clock_contexts_handoff=false;
    assert(clock_contexts_recover_export());assert(clock_contexts_tick()&&!clock_contexts_handoff&&ctx_requests==1);
    /* A rejected queued launch is also terminal until explicit retry. */
    assert(ctx_request(NULL,1));ctx_launch_ok=false;assert(clock_contexts_tick());assert(!ctx_view.export_pending&&!ctx_view.export_active&&!clock_contexts_handoff);ctx_launch_ok=true;
    unsigned calls=ctx_calls;held=1;assert(!clock_contexts_tick()&&ctx_calls==calls);held=0;
    ctx_view.audio=(contexts_source_status_v1){.source=1,.current=true,.room_valid=true,.event_valid=true,.model_state=CONTEXTS_MODEL_READY};
    strcpy(ctx_view.audio.room_name,"Study");strcpy(ctx_view.audio.event_name,"Door chime");
    clock_contexts_project(&ctx_view);assert(face.contexts.room_valid&&face.contexts.event_valid&&!strcmp(face.contexts.room,"Study"));
    ctx_view.radio=ctx_view.audio;ctx_view.radio.source=2;strcpy(ctx_view.radio.room_name,"Hall");
    clock_contexts_project(&ctx_view);assert(face.contexts.ambiguous&&!face.contexts.room_valid);ctx_view.radio.current=false;
    /* Copying pause status removes stale room/event labels from the face. */
    assert(clock_contexts_pause());assert(ctx_status(NULL,&ctx_view));clock_contexts_project(&ctx_view);assert(!face.contexts.room_valid&&!face.contexts.event_valid);
    assert(clock_contexts_tick()&&ctx_capturing);inject_alarm=true;
    assert(clock_alarm_pump_checked()&&!ctx_capturing);assert(clock_alarm_pump_checked());ctx_alarm=(alarm_status_v1){.api_version=1,.struct_size=sizeof(ctx_alarm),.state=ALARM_STATE_READY};
    /* Manual controls reserve the microphone before any output/preset work. */
    assert(clock_contexts_tick()&&ctx_capturing);clock_quick.ui.position_q8=PQA_OPEN_Q8;assert(clock_contexts_tick()&&!ctx_capturing);clock_quick.ui.position_q8=0;
    assert(clock_contexts_tick()&&ctx_capturing);sleep_mode=PORTABLE_SLEEP_LIGHT;
    assert(sleep_cycle()>=0&&!ctx_capturing&&sleeps==1);
    /* Long presentation and intentional frame waits service only capture. */
    ctx_capture_last=clock_ms;ctx_capture_gap=0;assert(pace_frame(clock_ms));assert(ctx_capture_gap<=8);
    unsigned captures=ctx_captures;reset_telemetry();risc_display_surface_v1 capture_surface={0};
    assert(frame(&capture_surface)&&draw_clock(clock_ms,&capture_surface));assert(ctx_captures>captures+30);
    scenario=14;ctx_capture_last=clock_ms;ctx_capture_gap=0;assert(present());assert(ctx_capture_gap<=8);scenario=30;
    /* Failure during rasterization retains its borrowed frame and prevents all later capability work. */
    assert(frame(&capture_surface));ctx_capture_ok=false;unsigned submit_before=submitted,release_before=released,polls_before=polls;
    assert(!draw_clock(clock_ms,&capture_surface)&&clock_contexts_uncertain&&ctx_retains==1&&held);
    captures=ctx_captures;assert(!present());sample_launcher_touch(clock_ms,true);assert(!frame(&capture_surface));
    assert(ctx_captures==captures&&submitted==submit_before&&released==release_before&&polls==polls_before);
    /* Fixture reset is outside the held invocation. */
    held=0;owned=false;clock_contexts_uncertain=false;ctx_capture_ok=true;
    assert(frame(&capture_surface)&&draw_clock(clock_ms,&capture_surface));ctx_refuse_pending=true;
    assert(!present()&&clock_contexts_uncertain&&ctx_retains==2&&pending&&!held);
    captures=ctx_captures;assert(!present());sample_launcher_touch(clock_ms,true);assert(ctx_captures==captures);
    pending=false;clock_display_settled=true;clock_contexts_uncertain=false;ctx_refuse_pending=false;
    assert(clock_contexts_pause());assert(portable_contexts_close(&clock_contexts));
    assert(grants==ungrants);
    assert(portable_contexts_open(&clock_contexts,rt));ctx_pause_ok=false;
    assert(!clock_contexts_pause()&&clock_contexts_uncertain);calls=ctx_calls;assert(!clock_contexts_tick()&&ctx_calls==calls);
    puts("Actual Clock: bounded owner handoffs/failures, live/ambiguous/stale projection, alarm/controls/sleep arbitration and retained fence PASS");return 0;
}
