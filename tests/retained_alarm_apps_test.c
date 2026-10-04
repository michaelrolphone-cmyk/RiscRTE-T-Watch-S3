#define PORTABLE_ALARM_CLIENT
#define PORTABLE_INPUT_NAVIGATION
#define PORTABLE_RETURN_APP "springboard.elf"
#define main original_settings_main
#include PORTABLE_SETTINGS_FIXTURE
#undef main
#include <setjmp.h>
static jmp_buf retained;
static alarm_status_v1 alarm_fake={.api_version=1,.struct_size=sizeof(alarm_fake)};
static unsigned service_steps,acks,stop_calls,retries,phases,pending_status_calls;
static bool output_bad,live_display;
static unsigned alarm_scenario;
static unsigned normal_after_failure;
static bool reset_after_ack(void*c){(void)c;return acks==0;}
static int32_t service_status(void*c,alarm_status_v1*out){(void)c;*out=alarm_fake;return ALARM_OK;}
static int32_t service_step(void*c){(void)c;assert(display_settled&&!live_display&&!surface.frame);service_steps++;if(failed)normal_after_failure++;
 if(alarm_fake.state==ALARM_STATE_LOADING){if(++phases==(alarm_scenario==8?10u:3u)){
   alarm_fake.state=ALARM_STATE_ALERT;
   if(alarm_scenario==8)alarm_fake.occurrence=(alarm_token_v1){ALARM_KIND_COUNTDOWN,8,88,10};
 }}
 if(alarm_fake.state==ALARM_STATE_DISMISSING){if(++phases==3){
   if(alarm_scenario==8&&acks==1){
     /* Production VERIFY_OCC clears active, then reloads all records before
        it can discover a second due identity. BACK cannot exit this gap. */
     alarm_fake.state=ALARM_STATE_LOADING;alarm_fake.occurrence=(alarm_token_v1){0};phases=0;
   }else if(alarm_scenario==6&&acks==1){alarm_fake.state=ALARM_STATE_ALERT;alarm_fake.occurrence.generation++;}
   else{alarm_fake.state=ALARM_STATE_READY;alarm_fake.occurrence=(alarm_token_v1){0};}
 }}
 return ALARM_OK;}
static int32_t service_refresh(void*c){(void)c;retries++;alarm_fake.state=ALARM_STATE_READY;return ALARM_PENDING;}
static int32_t service_ack(void*c,const alarm_token_v1*t){(void)c;assert(!memcmp(t,&alarm_fake.occurrence,sizeof(*t)));acks++;phases=0;if(alarm_scenario==7&&acks==1){alarm_fake.occurrence.generation++;return ALARM_STALE;}alarm_fake.state=ALARM_STATE_DISMISSING;return ALARM_PENDING;}
static int32_t service_prepare(void*c,alarm_sleep_v1*s){(void)c;(void)s;assert(!"unexpected sleep");return ALARM_INVALID;}
static int32_t service_stop(void*c){(void)c;stop_calls++;assert(stop_calls<=3);return stop_calls<3?ALARM_PENDING:output_bad?ALARM_OUTPUT:ALARM_OK;}
static const alarm_service_v1 service_api={1,sizeof(service_api),NULL,service_status,service_step,service_refresh,service_ack,service_prepare,service_stop};
static bool acquire_alarm(const char*name,uint32_t version,uint64_t instance,risc_runtime_capability_v1*out){
 if(!strcmp(name,ALARM_SERVICE_CAPABILITY)){assert(version==1&&!instance);out->api=&service_api;out->slot=100;++grants;return true;}
 return runtime_api.acquire(name,version,instance,out);
}
static void yield_retained(uint32_t ms){if(alarm_failed_cleaned&&output_bad)longjmp(retained,1);test_yield(ms);}
static bool frame_delayed(void*c,risc_display_present_token_v1 token,risc_display_present_status_v1*out){
 (void)c;(void)token;pending_status_calls++;
 assert(!service_steps);if(pending_status_calls<3){live_display=true;out->state=RISC_DISPLAY_PRESENT_ACTIVE;}else{live_display=false;out->state=RISC_DISPLAY_PRESENT_COMPLETE;}return true;}

#ifdef TEST_CALCULATOR
#define app_main retained_calculator_main
#include UTILITIES_APP_SOURCE
#undef app_main
#else
#define app stopwatch_app
#define rtc stopwatch_rtc
#define rtc_grant stopwatch_rtc_grant
#define status stopwatch_status
#define app_main retained_stopwatch_main
#include UTILITIES_APP_SOURCE
#undef app
#undef rtc
#undef rtc_grant
#undef status
#undef app_main
#endif
int main(void) { (void)frame_delayed; (void)reset_after_ack;
    scenario=100;
    risc_runtime_api_v1 r=runtime_api;r.acquire=acquire_alarm;r.yield_ms=yield_retained;rt=&r;
    dg.struct_size=sizeof(dg);assert(acquire_alarm("display.output",1,0,&dg));display=dg.api;
    assert(display_info(NULL,&info));assert(portable_touch_open(&touch,&r));
    display_settled=true;alarm_pixels=malloc(sizeof(framebuffer));assert(alarm_pixels);assert(portable_alarm_open(&alarms,&r));
#ifdef TEST_CALCULATOR
    calculator_api=&app;calculator_width=calculator_height=240;calculator_selected=0;calculator_pressed=-1;
    calc_reset(&calculator_state);calc_key(&calculator_state,'8');calc_key(&calculator_state,'+');calc_key(&calculator_state,'2');calc_key(&calculator_state,'=');
    calculator expected=calculator_state;calculator_render();
#else
    stopwatch_app=&app;loaded=true;pending_pause=reset_armed=false;
    clock_state=(sw_clock){.saved={1000,0,true,false},.elapsed_ms=1000,.last_ms=ticks,.running=true};
    stopwatch_status="RUNNING";draw();sw_clock expected=clock_state;
#endif
    alarm_fake.state=ALARM_STATE_ALERT;alarm_fake.occurrence=(alarm_token_v1){1,1,42,1};
    tap(3,100,180);bool consumed=false;uint32_t before=ticks;(void)before;
    assert(alarm_foreground(&consumed)&&consumed&&!return_launches&&acks==1);
#ifdef TEST_CALCULATOR
    assert(!memcmp(&calculator_state,&expected,sizeof(expected)));calc_key(&calculator_state,'=');assert(!strcmp(calculator_state.text,"12"));
    /* Pending operator/error/repeat are the same original model, never reopened. */
    calc_key(&calculator_state,'/');calc_key(&calculator_state,'0');calc_key(&calculator_state,'=');assert(calculator_state.error==CALC_DIV_ZERO);
#else
    assert(!memcmp(&clock_state,&expected,sizeof(expected)));sw_tick(&clock_state,ticks);
    assert(clock_state.elapsed_ms==1000+ticks-before&&clock_state.running&&!clock_state.approximate);
    pending_pause=true;clock_state.running=false;clock_state.clock_changed=true;expected=clock_state;
    /* A second alert preserves the pending storage/error path verbatim. */
    alarm_fake.state=ALARM_STATE_ALERT;alarm_fake.occurrence=(alarm_token_v1){2,2,44,2};tap(polls+3,100,180);
    assert(alarm_foreground(&consumed)&&consumed);assert(pending_pause&&!memcmp(&clock_state,&expected,sizeof(expected)));
#endif
    app_module_fini();assert(!grants&&!subscriptions&&!frame_count);
    puts("Actual foreground application model/render: retained exact state and no synthetic app handoff passed");
}
