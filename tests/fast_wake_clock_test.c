/* Production Clock and renderer; fake device/API boundaries and explicit costs.
 * No host wall-clock measurement is reported as ESP32 hardware timing. */
#define WATCH_CONTEXTS_CLIENT
#define WATCH_RUNTIME_FEATURES
#define WATCH_BLE_BROADCAST
#define WATCH_PAIRED_BOOT_CONFIRM
#define WATCH_CLOCK_ALARMS
#define WATCH_CLOCK_POINTS
#define WATCH_MOTION_WAKE
#define WATCH_ALARM_SLEEP_RESUME
#define WATCH_QUICK_RADIOS
#define PORTABLE_LOW_BATTERY
#define main inherited_quick_fixture_main
#define WATCH_TEST_RUNTIME_EXTERN
#include "quick_clock_test.c"

#undef main

static uint32_t boot_cause,checkpoint_result,retains,confirmations,promotions;
static uint32_t service_acquires,first_at,service_input_polls,last_service_polls;
static uint32_t first_frames,soft_frames,wake_began,soft_latency,input_at,input_stages;
static uint32_t fake_service_cost,transfer_cost,fail_service,stage_calls;
static uint32_t wake_count,requested_wakes,alarm_frames,seed_calls;
static bool ended,early_launch,first_seen,fail_display,fail_release;
static bool fail_context_pause,confirmed_early,unset_time;
static bool retained_fence,swipe_during_frame,swipe_latched,low_on_wake;
static bool broadcast_live,contexts_live,contexts_enabled,alarm_on_wake;
static bool fail_broadcast_restart,fail_ble_enable,early_sleep;
static bool expect_context_handoff,queued_context_handoff;
static uint32_t broadcast_starts,contexts_starts,broadcast_at,contexts_at;
static uint32_t resume_input_at,radio_at,frame_at,radio_apply_count;
static uint32_t motion_prepares,motion_resumes,motion_sleeps,alarm_resumes,points_loads;
static uint32_t service_start_cost,broadcast_frame;
static char wake_stages[128][32];
static uint32_t wake_stage_times[128],wake_stage_count;
static uint32_t display_load_cost,sleep_setting_cost,sleep_setting_reads;
static uint32_t alarm_load_cost,alarm_acquires,rtc_acquires;
static bool crown_before_alarm,fail_late_rtc_read,late_rtc_retention,native_context_failed;
static uint32_t prealarm_crown_events;
static const char *fail_capability;
static bool fail_frame_acquire,fail_unblank,fail_marker_sample,fail_next_health;
static unsigned fail_sleep_acquire,refused_cycles,refused_restores,clean_refusal_frames,sleep_acquire_errors;
static bool sleep_failure_armed;
static void check_refusal_pixels(void){
 risc_display_surface_v1 expected={0,expected_pixels,240,240,480,sizeof(expected_pixels),5};
 assert(nova_watch_face_render(&expected,&face,picker.selected));
 if(sleep_status[0]){
  /* A genuine error may change only the existing status strip. */
  for(unsigned y=0;y<240;y++)for(unsigned x=0;x<240;x++)
   if(y<203||y>=231||x<10||x>=230)assert(completed_pixels[y*240+x]==expected_pixels[y*240+x]);
  assert(memcmp(completed_pixels,expected_pixels,sizeof(expected_pixels)));
  assert(nova_watch_sleep_status(&expected,sleep_status));
 }
 assert(!memcmp(completed_pixels,expected_pixels,sizeof(expected_pixels)));
}
static unsigned stage_count(const char *name) {
 unsigned found=0;for(unsigned i=0;i<wake_stage_count;i++)found+=!strcmp(name,wake_stages[i]);return found;
}
static unsigned stage_index(const char *name) {
 for(unsigned i=0;i<wake_stage_count;i++)if(!strcmp(name,wake_stages[i]))return i;
 assert(false);return 0;
}
static void check_io(void){assert(!retained_fence);}
static risc_realtime_snapshot_v1 native_time;
static alarm_status_v1 alarm_view;
static contexts_status_v1 contexts_view;
static int32_t native_read(void*c,risc_realtime_snapshot_v1*out){check_io();(void)c;if(native_context_failed)return RISC_REALTIME_CONTEXT;*out=native_time;return 0;}
static int32_t native_seed(void*c,int64_t seconds,uint32_t ns){check_io();(void)c;assert(!ns);seed_calls++;native_time.epoch_seconds=seconds;native_time.validity=1;return 0;}
static int32_t wake_read(void*c,uint32_t type,uint32_t schema,risc_retained_wake_record_v1*out,uint32_t*cause){
 check_io();(void)c;*cause=boot_cause;*out=(risc_retained_wake_record_v1){.struct_size=sizeof(*out),.type=type,.schema_version=schema,.size=1,.payload={1}};return checkpoint_result;}
static int32_t wake_stage(void*c,const risc_retained_wake_record_v1*r){check_io();(void)c;assert(r->size==1);return 0;}
static int32_t wake_clear(void*c){check_io();(void)c;return 0;}
static int32_t native_promote(void*c){check_io();(void)c;promotions++;return 0;}
static const risc_realtime_control_api_v1 native_api={1,sizeof(native_api),NULL,native_read,native_seed};
static const risc_retained_wake_api_v1 wake_api={1,sizeof(wake_api),NULL,wake_read,wake_stage,wake_clear};
static const risc_provider_promotion_api_v1 promote_api={1,sizeof(promote_api),NULL,native_promote};
static bool fast_retain(void){retains++;retained_fence=true;return true;}
static bool fast_confirm(void){check_io();assert(!queued_context_handoff);confirmations++;if(service_acquires<4)confirmed_early=true;return true;}
static bool fast_health(risc_runtime_health_v1*h){check_io();h->uptime_ms=clock_ms;if(fail_next_health){fail_next_health=false;return false;}return !ended&&clock_ms<30000u;}
static bool fast_diagnostic(const char*s){
 if(!strncmp(s,"WATCH_SLEEP error=",18)){
  const char *expected=fail_sleep_acquire==1?
   "WATCH_SLEEP error=settings-acquire capability=storage.key-value instance=1":
   "WATCH_SLEEP error=motion-acquire capability=motion.accel instance=7";
  assert(fail_sleep_acquire&&!strcmp(s,expected));sleep_acquire_errors++;
 }
 if(!strncmp(s,"WATCH_CLOCK sleep=refused",25)){
  const char *expected=fail_sleep_acquire==1?"WATCH_CLOCK sleep=refused stage=SETTINGS detail=unavailable":
   "WATCH_CLOCK sleep=refused stage=MOTION detail=unavailable";
  assert(fail_sleep_acquire&&!strcmp(s,expected));
  assert(!strcmp(sleep_status,fail_sleep_acquire==1?"SLEEP ERR SETTINGS":"SLEEP ERR MOTION"));
  assert(!hardware_brightness&&!owned&&!pending&&!touch.subscription);
  refused_cycles++;
 }
 if(!strncmp(s,"WATCH_WAKE stage=",17)) {
  assert(wake_stage_count<128);unsigned now,elapsed;
  assert(sscanf(s,"WATCH_WAKE stage=%31s t_ms=%u elapsed_ms=%u",wake_stages[wake_stage_count],&now,&elapsed)==3);
  assert(now==clock_ms&&elapsed==clock_ms-clock_wake_started);
  wake_stage_times[wake_stage_count++]=now;
  if(fail_marker_sample&&!strcmp(wake_stages[wake_stage_count-1],"display-begin"))fail_next_health=true;
 }
 if(!strcmp(s,"WATCH_CLOCK ready crown=enabled")){ready=true;ready_time=clock_ms;}
 if(strstr(s,"stage=first-frame")){assert(!first_seen);first_seen=true;first_at=clock_ms;first_frames=submitted;
  assert(hardware_brightness==clock_quick.brightness&&!pending&&!owned&&touch.subscription&&last_complete==submitted);assert(service_acquires==0);
  assert(points_loads==1&&face.points==&clock_points_view&&!sleep_setting_reads&&!alarm_acquires&&!alarm_frames);
  if(face.time_valid){twatch_rtc_time_v1 raw={0},expected={0};assert(watch_runtime_calendar(native_time.epoch_seconds,&raw));assert(watch_display_time(&raw,&expected));assert(!memcmp(&face.time,&expected,sizeof(expected)));}
  risc_display_surface_v1 expected={0,expected_pixels,240,240,480,sizeof(expected_pixels),5};assert(nova_watch_face_render(&expected,&face,picker.selected));assert(!memcmp(completed_pixels,expected_pixels,sizeof(expected_pixels)));
  if(early_launch)launcher_swipe_pending=true;
 }
 if(strstr(s,"stage=first-input-poll")){input_at=clock_ms;input_stages++;assert(touch.subscription&&polls);if(wake_count)resume_input_at=clock_ms;}
 if(strstr(s,"stage=light-resume")){wake_began=clock_ms;assert(!clock_quick.ui.radios_valid&&!clock_radios.valid&&!clock_radios.available);assert(!clock_broadcast_started&&!clock_contexts_started);}
 if(strstr(s,"stage=light-frame")){soft_frames++;soft_latency=clock_ms-wake_began;assert(!pending&&!owned&&hardware_brightness==clock_quick.brightness);
  assert(!sleep_status[0]);if(refused_restores)check_refusal_pixels();
 }
 if(strstr(s,"stage=radios-begin")){radio_at=clock_ms;assert(input_stages>0);if(wake_count)assert(resume_input_at>=wake_began);assert(frame_at>=(wake_count?wake_began:first_at));}
 if(strstr(s,"stage=broadcast-begin"))broadcast_at=clock_ms;
 if(strstr(s,"stage=contexts-begin"))contexts_at=clock_ms;
 if(strstr(s,"stage=services-ready")){stage_calls++;if(wake_count+refused_cycles==requested_wakes&&!early_launch)ended=true;}
 return true;
}
static bool fast_status(void*c,uint64_t token,risc_display_present_status_v1*out){
 check_io();(void)c;assert(token==submitted&&pending);
 if(swipe_during_frame&&first_seen&&submitted==2&&clock_ms-frame_started>=10&&!swipe_latched){launcher_swipe_pending=true;swipe_latched=true;swipe_time=clock_ms;}
 if(clock_ms-frame_started<transfer_cost){out->state=RISC_DISPLAY_PRESENT_ACTIVE;return true;}
 pending=false;out->state=fail_display?RISC_DISPLAY_PRESENT_FAILED:RISC_DISPLAY_PRESENT_COMPLETE;
 if(!fail_display){memcpy(completed_pixels,pixels,sizeof(pixels));last_complete=submitted;frame_at=clock_ms;if(clock_alarm_modal)alarm_frames++;
  if(refused_restores&&hardware_brightness){
   check_refusal_pixels();clean_refusal_frames++;
  }
 }return true;
}
static bool fast_frame_acquire(void*c,uint32_t format,risc_display_surface_v1*out) {
 check_io();return !fail_frame_acquire&&acquire_frame(c,format,out);
}
static bool fast_brightness(void*c,uint16_t level,uint16_t maximum) {
 if(level&&refused_cycles>refused_restores){
  assert(!owned&&!pending&&last_complete==submitted&&!hardware_brightness);
  assert(sleep_status[0]);check_refusal_pixels();refused_restores++;
 }
 check_io();return !(level&&fail_unblank)&&brightness(c,level,maximum);
}
static bool fast_key(void*c,uint32_t*out){check_io();(void)c;*out=0;
 if(crown_before_alarm&&ready&&!alarm_acquires){*out=2;crown_before_alarm=false;prealarm_crown_events++;}
 else if(clock_alarm_modal&&alarm_view.occurrence.generation&&alarm_frames)*out=1;
 else if(first_seen&&(clock_deferred_phase==4||(early_sleep&&clock_deferred_phase==1))&&wake_count+refused_cycles<requested_wakes&&clock_ms-ready_time>300){*out=2;sleep_failure_armed=fail_sleep_acquire!=0&&refused_cycles<2;}
 return true;}
static int32_t fast_sleep(void*c,risc_light_sleep_result_v1*out){check_io();(void)c;(void)out;assert(!touch.subscription&&!ble_state&&!pending&&!owned);assert(!broadcast_live&&!contexts_live);sleeps++;wake_count++;clock_ms+=500;native_time.epoch_seconds+=3600;if(low_on_wake){low_percent=5;clock_low_battery_sampled=false;}if(alarm_on_wake){alarm_view.state=ALARM_STATE_ALERT;alarm_view.occurrence.generation=1;}return RISC_LIGHT_SLEEP_OK;}
static int32_t fast_sleep_timed(void*c,uint32_t ms,risc_light_sleep_result_v1*out){(void)ms;return fast_sleep(c,out);}
static bool fast_rtc(void*c,twatch_rtc_time_v1*out){if(fail_late_rtc_read){native_context_failed=late_rtc_retention;return false;}if(unset_time){memset(out,0,sizeof(*out));return true;}return rtc_read(c,out);}
static int32_t alarm_status(void*c,alarm_status_v1*out){check_io();(void)c;*out=alarm_view;return 0;}
static int32_t alarm_step(void*c){check_io();(void)c;return 0;}
static int32_t alarm_refresh(void*c){check_io();(void)c;return 0;}
static int32_t alarm_ack(void*c,const alarm_token_v1*token){check_io();(void)c;assert(token->generation);alarm_view.state=ALARM_STATE_READY;alarm_view.occurrence.generation=0;return 0;}
static int32_t alarm_prepare(void*c,alarm_sleep_v1*out){check_io();(void)c;*out=(alarm_sleep_v1){.struct_size=sizeof(*out)};return 0;}
static int32_t alarm_resume(void*c,const alarm_sleep_v1*plan){check_io();(void)c;assert(plan->struct_size==sizeof(*plan));alarm_resumes++;return ALARM_OK;}
static const alarm_service_sleep_v1 alarm_api={{1,sizeof(alarm_api),NULL,alarm_status,alarm_step,alarm_refresh,alarm_ack,alarm_prepare,alarm_refresh},alarm_resume};
static bool motion_prepare(void*c){check_io();(void)c;motion_prepares++;return true;}
static bool motion_resume(void*c){check_io();(void)c;motion_resumes++;return true;}
static bool motion_pending(void*c,bool*out){check_io();(void)c;*out=false;return true;}
static bool motion_info(void*c,twatch_tap_info_v1*out){check_io();(void)c;*out=(twatch_tap_info_v1){sizeof(*out),TWATCH_TAP_BMA423,0,7,3};return true;}
static bool motion_configure(void*c,uint16_t value){check_io();(void)c;assert(value==3);return true;}
static bool motion_observe(void*c,twatch_tap_observation_v1*out){check_io();(void)c;(void)out;assert(false);return false;}
static const twatch_motion_api_v1 motion_api={.api_version=1,.struct_size=sizeof(motion_api),.prepare_wake=motion_prepare,.wake_pending=motion_pending,.resume_wake=motion_resume,.tap_info=motion_info,.tap_configure=motion_configure,.tap_observe_begin=motion_configure,.tap_observe=motion_observe};
static int32_t motion_sleep(void*c,uint32_t ms,risc_light_sleep_result_v1*out){check_io();motion_sleeps++;assert(motion_prepares==motion_sleeps);return fast_sleep_timed(c,ms,out);}
static int32_t motion_deep(void*c,uint32_t ms){check_io();(void)c;(void)ms;assert(false);return RISC_DEEP_SLEEP_UNSUPPORTED;}
static bool context_pause(void*c){check_io();(void)c;assert(!held&&!pending);contexts_live=false;return !fail_context_pause;}
static bool context_step(void*c,const contexts_policy_v1*p){check_io();(void)c;assert(!held&&!pending&&!clock_radios_pending&&clock_contexts_started);
 assert(!queued_context_handoff);
 if(!contexts_live){assert(clock_deferred_phase==2&&clock_ms>=contexts_at&&frame_at<=contexts_at&&submitted>broadcast_frame);contexts_live=true;contexts_starts++;clock_ms+=service_start_cost;}
 assert(!p->enabled||contexts_enabled);if(low_percent<10)assert(!p->audio_allowed&&!p->radio_allowed);
 return true;}
static bool context_status(void*c,contexts_status_v1*out){check_io();(void)c;*out=contexts_view;return true;}
static bool context_request(void*c,uint32_t sources){check_io();(void)c;(void)sources;return true;}
static bool context_begin(void*c,uint32_t source){check_io();(void)c;contexts_view.export_active=source;return true;}
static bool context_export(void*c,uint32_t s,uint32_t k,uint32_t i,const void*b,uint32_t n){check_io();(void)c;(void)s;(void)k;(void)i;(void)b;(void)n;return true;}
static bool context_finish(void*c,uint32_t source,uint32_t result){check_io();(void)c;(void)source;(void)result;return true;}
static int32_t context_label(void*c,uint32_t s,uint32_t i,contexts_label_v1*out){check_io();(void)c;(void)s;(void)i;(void)out;return 0;}
static bool context_claim(void*c,uint32_t s,uint32_t i,const char*n,uint32_t g){check_io();(void)c;(void)s;(void)i;(void)n;(void)g;return false;}
static bool context_result(void*c,uint32_t s,uint32_t g,uint32_t r){check_io();(void)c;(void)s;(void)g;(void)r;return true;}
static bool context_capture(void*c){check_io();(void)c;return true;}
static const contexts_service_v1 context_api={.api_version=1,.struct_size=sizeof(context_api),.step=context_step,.pause=context_pause,.status=context_status,.request_export=context_request,.begin_export=context_begin,.export_record=context_export,.finish_export=context_finish,.label=context_label,.claim_preset=context_claim,.preset_result=context_result,.capture_audio=context_capture};
static bool broadcast_step(void*c,bool allowed,const telemetry_broadcast_policy_v1*p){check_io();(void)c;assert(allowed&&!clock_radios_pending&&clock_broadcast_started);
 assert(!queued_context_handoff);
 if(!broadcast_live){assert(clock_deferred_phase==1&&clock_ms>=broadcast_at&&frame_at<=broadcast_at);broadcast_frame=submitted;broadcast_live=true;broadcast_starts++;clock_ms+=service_start_cost;}
 assert(!p->radios_allowed||(!clock_quick.ui.airplane&&clock_quick.ui.bluetooth_enabled));
 return !(fail_broadcast_restart&&wake_count);}
static bool broadcast_pause(void*c){check_io();(void)c;broadcast_live=false;return true;}
static bool broadcast_status(void*c,telemetry_broadcast_status_v1*out){(void)c;memset(out,0,sizeof(*out));return true;}
static int32_t broadcast_enumerate(void*c,uint32_t index,risc_telemetry_field_v1*out){(void)c;(void)index;(void)out;return false;}
static int32_t broadcast_read(void*c,uint32_t id,int32_t*out){(void)c;(void)id;(void)out;return 0;}
static const telemetry_broadcast_v1 broadcast_api={.api_version=1,.struct_size=sizeof(broadcast_api),.step=broadcast_step,.pause=broadcast_pause,.status=broadcast_status,.enumerate=broadcast_enumerate,.read=broadcast_read};
static const portable_bluetooth_control_v1 fast_ble;
static const risc_key_value_v1 fast_kv;
static bool fast_acquire(const char*n,uint32_t version,uint64_t instance,risc_runtime_capability_v1*g){
 check_io();
 if(sleep_failure_armed&&((fail_sleep_acquire==1&&!strcmp(n,RISC_KEY_VALUE_CAPABILITY)&&instance==1)||
    (fail_sleep_acquire==2&&!strcmp(n,TWATCH_MOTION_CAPABILITY)&&instance==7))){
  assert(!hardware_brightness&&!touch.subscription&&!pending&&!owned&&!broadcast_live&&!contexts_live);
  for(unsigned pixel=0;pixel<240u*240u;pixel++)assert(!completed_pixels[pixel]);
  sleep_failure_armed=false;return false;
 }
 if(fail_capability&&!strcmp(n,fail_capability))return false;
 if(!strcmp(n,"display.output"))clock_ms+=display_load_cost;
 if(!strcmp(n,"rtc.clock"))rtc_acquires++;
 if(!strcmp(n,ALARM_SERVICE_CAPABILITY)){
  assert(first_seen&&input_stages&&!pending&&!owned&&!service_acquires);
  alarm_acquires++;clock_ms+=alarm_load_cost;
 }
 if(!strcmp(n,"net.wifi")||!strcmp(n,"bluetooth.hci")||!strcmp(n,TELEMETRY_BROADCAST_CAPABILITY)||!strcmp(n,CONTEXTS_SERVICE_CAPABILITY)){
  assert(first_seen&&!pending&&!owned);service_acquires++;service_input_polls=polls;
  if(clock_radios_pending)assert(radio_at&&input_stages);
  /* Two radio grants are one synchronous policy stage; later stages require
   * another foreground input opportunity and another completed clock frame. */
  if(service_acquires==3||service_acquires==4)assert(polls>last_service_polls);
  last_service_polls=polls;clock_ms+=fake_service_cost;if(fail_service==service_acquires)return false;
 }
 const void*p=NULL;
 if(!strcmp(n,RISC_REALTIME_CONTROL_CAPABILITY))p=&native_api;
 else if(!strcmp(n,RISC_RETAINED_WAKE_CAPABILITY))p=&wake_api;
 else if(!strcmp(n,RISC_PROVIDER_PROMOTION_CAPABILITY))p=&promote_api;
 else if(!strcmp(n,ALARM_SERVICE_CAPABILITY))p=&alarm_api;
 else if(!strcmp(n,TELEMETRY_BROADCAST_CAPABILITY))p=&broadcast_api;
 else if(!strcmp(n,CONTEXTS_SERVICE_CAPABILITY))p=&context_api;
 else if(!strcmp(n,TWATCH_MOTION_CAPABILITY)){assert(instance==7);p=&motion_api;}
 else if(!strcmp(n,RISC_KEY_VALUE_CAPABILITY)&&instance==5){points_loads++;g->api=&fast_kv;grants++;return true;}
 if(p){assert(version==1&&(!instance||instance==7));g->api=p;grants++;return true;}
 bool acquired=acquire_cap(n,version,instance,g);
 if(acquired&&g->api==&qa_ble)g->api=&fast_ble;
 if(acquired&&g->api==&face_kv)g->api=&fast_kv;
 return acquired;
}
static bool fast_release(risc_runtime_capability_v1*g){check_io();if(fail_release&&g->api==&context_api){fail_release=false;return false;}return release_cap(g);}
static bool fast_launch(const char*path){check_io();assert(!held&&!pending);
 if(expect_context_handoff){assert(!strcmp(path,"waterfall.elf")&&!queued_context_handoff);queued_context_handoff=true;}
 else{assert(!strcmp(path,"springboard.elf")&&!touch.subscription);ended=true;}
 launches++;return true;}
static bool fast_snapshot(void*c,risc_touch_snapshot_v1*out){check_io();(void)c;*out=(risc_touch_snapshot_v1){.width=240,.height=240};return true;}
static bool fast_ble_enable(void*c,bool enabled){check_io();radio_apply_count++;if(fail_ble_enable)return false;return ble_enable(c,enabled);}
static bool fast_ble_status(void*c,uint8_t*out){check_io();return ble_status(c,out);}
static const portable_bluetooth_control_v1 fast_ble={.api_version=1,.struct_size=sizeof(fast_ble),.set_enabled=fast_ble_enable,.status=fast_ble_status};
static int32_t fast_get(void*c,const char*k,void*b,uint32_t n,uint32_t*z){check_io();
 if(!strcmp(k,PORTABLE_SLEEP_KEY)){sleep_setting_reads++;clock_ms+=sleep_setting_cost;}
 if(!strcmp(k,PORTABLE_CONTEXT_ENABLED_KEY)&&contexts_enabled){assert(n>=4);memcpy(b,(uint8_t[]){0x43,1,1,1^0xa5},4);*z=4;return RISC_KEY_VALUE_OK;}
 return face_get(c,k,b,n,z);}
static const risc_key_value_v1 fast_kv={1,sizeof(fast_kv),NULL,fast_get,face_put};
static const struct {risc_runtime_api_v1 prefix;bool(*confirm)(void);bool(*retain)(void);} fast_runtime={{1,sizeof(fast_runtime),fast_health,yield,fast_diagnostic,fast_launch,fast_acquire,fast_release},fast_confirm,fast_retain};
const risc_runtime_api_v1*risc_runtime_get_api(uint32_t version){assert(version==1);return &fast_runtime.prefix;}
static void reset_case(void){
 (void)runtime;
 assert(!allocations);scenario=30;clock_ms=submitted=released=grants=ungrants=subscribed=unsubscribed=polls=launches=sleeps=touch_step=0;
 ready=owned=pending=launched=false;last_complete=swipe_submitted=swipe_time=0;hardware_brightness=40;
 boot_cause=RISC_BOOT_RESET;checkpoint_result=RISC_RETAINED_WAKE_ABSENT;retains=confirmations=promotions=0;
 service_acquires=first_at=service_input_polls=last_service_polls=first_frames=soft_frames=wake_began=soft_latency=input_at=input_stages=0;
 fake_service_cost=700;transfer_cost=95;fail_service=stage_calls=0;wake_count=requested_wakes=alarm_frames=seed_calls=0;
 ended=early_launch=first_seen=fail_display=fail_release=fail_context_pause=confirmed_early=unset_time=false;
 retained_fence=swipe_during_frame=swipe_latched=low_on_wake=false;
 broadcast_live=contexts_live=contexts_enabled=alarm_on_wake=false;
 fail_broadcast_restart=fail_ble_enable=early_sleep=false;
 expect_context_handoff=queued_context_handoff=false;
 broadcast_starts=contexts_starts=broadcast_at=contexts_at=0;
 resume_input_at=radio_at=frame_at=radio_apply_count=0;
 motion_prepares=motion_resumes=motion_sleeps=alarm_resumes=points_loads=broadcast_frame=0;service_start_cost=400;
 wake_stage_count=display_load_cost=sleep_setting_cost=sleep_setting_reads=0;
 alarm_load_cost=alarm_acquires=rtc_acquires=0;
 crown_before_alarm=fail_late_rtc_read=late_rtc_retention=native_context_failed=false;prealarm_crown_events=0;
 fail_capability=NULL;fail_frame_acquire=fail_unblank=fail_marker_sample=fail_next_health=false;
 fail_sleep_acquire=refused_cycles=refused_restores=clean_refusal_frames=sleep_acquire_errors=0;sleep_failure_armed=false;
 low_percent=55;low_flags=0;low_read_fail=false;memset(low_lengths,0,sizeof(low_lengths));memset(low_writes,0,sizeof(low_writes));
 saved_face=radio_saved=false;ble_state=0;face_writes=face_reads=0;memset(quick_saved,0,sizeof(quick_saved));
 da.base.present_status=fast_status;pa.key_events=fast_key;pa.light_sleep=fast_sleep;pa.light_sleep_for=fast_sleep_timed;ra.read=fast_rtc;
 da.base.acquire=fast_frame_acquire;da.base.set_brightness=fast_brightness;
 pa.light_sleep_set=motion_sleep;pa.deep_sleep_set=motion_deep;ta.snapshot=fast_snapshot;
 native_time=(risc_realtime_snapshot_v1){.struct_size=sizeof(native_time),.validity=RISC_REALTIME_VALID,.epoch_seconds=1791074400};
 alarm_view=(alarm_status_v1){.api_version=1,.struct_size=sizeof(alarm_view),.state=ALARM_STATE_READY};
 contexts_view=(contexts_status_v1){.struct_size=sizeof(contexts_view)};
 contexts_view.audio.model_state=contexts_view.radio.model_state=CONTEXTS_MODEL_READY;
}
static void check_clean(void){assert(!retained_fence&&!held&&!pending&&!owned&&!allocations);assert(grants==ungrants);assert(subscribed==unsubscribed);assert(!confirmed_early);assert(motion_prepares==wake_count&&motion_resumes==wake_count&&motion_sleeps==wake_count&&alarm_resumes==wake_count);}
static void retained_reset(void){assert(retained_fence&&!allocations);grants=ungrants;subscribed=unsubscribed;owned=pending=false;held=0;}
static void saved_radio(uint8_t flags){radio_saved=true;memcpy(radio_bytes,(uint8_t[]){0x51,1,flags,(uint8_t)(flags^0xa5)},4);}
static void check_boot_stages(void) {
 static const char *const expected[]={"entry","runtime-grants-begin","runtime-grants-end",
  "display-begin","display-end","battery-begin","battery-end","rtc-begin","rtc-end",
  "settings-begin","settings-end","points-begin","points-end",
  "touch-begin","touch-end","render-begin","render-end",
  "transfer-begin","transfer-end","unblank-begin","unblank-end","first-frame",
  "sleep-settings-begin","sleep-settings-end","first-input-poll",
  "alarm-begin","alarm-end","reconcile-begin","reconcile-end"};
 assert(wake_stage_count>=sizeof(expected)/sizeof(*expected));
 for(unsigned i=0,j=0;i<sizeof(expected)/sizeof(*expected);i++,j++) {
  if(!strcmp(wake_stages[j],"rtc-deferred"))j++;
  assert(j<wake_stage_count&&!strcmp(wake_stages[j],expected[i]));
 }
 assert(stage_count("first-frame")==1&&stage_count("entry")==1);
}
static char diagnostic_line[80];
static bool capture_diagnostic(const char *line){assert(strlen(line)<sizeof(diagnostic_line));strcpy(diagnostic_line,line);return false;}
static void check_refusal_diagnostics(void){
 static const risc_runtime_api_v1 capture={.diagnostic=capture_diagnostic};
 static const char *const stages[]={"UNKNOWN","SENSOR","PANEL","PMU","ALARM","LIGHT","DEEP","ACQUIRE","API","SETTINGS","MOTION","RUNTIME","UNKNOWN"};
 static const int32_t details[]={0,-1,17,INT32_MIN,INT32_MAX};
 const risc_runtime_api_v1 *saved=rt;rt=&capture;
 memcpy(expected_pixels,pixels,sizeof(pixels));
 for(unsigned stage=0;stage<13;stage++)for(unsigned detail=0;detail<5;detail++){
  watch_sleep_stage=stage;watch_sleep_detail=details[detail];clock_sleep_refused();
  bool has_detail=stage<9||stage>11;
  char expected[80];
  if(has_detail)snprintf(expected,sizeof(expected),"WATCH_CLOCK sleep=refused stage=%s detail=%ld",stages[stage],(long)details[detail]);
  else snprintf(expected,sizeof(expected),"WATCH_CLOCK sleep=refused stage=%s detail=unavailable",stages[stage]);
  assert(!strcmp(diagnostic_line,expected)&&!memcmp(pixels,expected_pixels,sizeof(pixels)));
  if(has_detail)snprintf(expected,sizeof(expected),"SLEEP ERR %s %ld",stages[stage],(long)details[detail]);
  else snprintf(expected,sizeof(expected),"SLEEP ERR %s",stages[stage]);
  assert(!strcmp(sleep_status,expected));
 }
 watch_sleep_stage=0;watch_sleep_detail=0;sleep_status[0]=0;rt=saved;
}
int main(void){
 /* Inject five-minute errors in both directions at every deep-wake cause.
  * The first frame/input stays fast; settled display must follow read-only RTC. */
 for(unsigned cause=RISC_BOOT_DEEP_TIMER;cause<=RISC_BOOT_DEEP_OTHER;cause++)for(int sign=-1;sign<=1;sign+=2) {
  reset_case();boot_cause=cause;twatch_rtc_time_v1 raw,expected;int64_t hardware_epoch;
  assert(rtc_read(NULL,&raw)&&watch_runtime_epoch(&raw,&hardware_epoch));
  native_time.epoch_seconds=hardware_epoch+sign*300;
  app_main();check_clean();assert(first_at==95&&input_at==95&&seed_calls==1&&rtc_acquires==1);
  assert(native_time.epoch_seconds==hardware_epoch&&watch_display_time(&raw,&expected));
  assert(face.time_valid&&!memcmp(&face.time,&expected,sizeof(expected)));
 }
 for(unsigned failure=0;failure<2;failure++) {
  reset_case();boot_cause=RISC_BOOT_DEEP_GPIO;
  if(failure)fail_late_rtc_read=true;else fail_capability="rtc.clock";
  int64_t retained_epoch=native_time.epoch_seconds;app_main();check_clean();
  assert(first_at==95&&input_at==95&&confirmations==1&&service_acquires==4&&!seed_calls);
  assert(face.time_valid&&native_time.epoch_seconds==retained_epoch&&!strcmp(sleep_status,"TIME CHECK ERR"));
 }
 reset_case();boot_cause=RISC_BOOT_DEEP_GPIO;fail_late_rtc_read=late_rtc_retention=true;
 app_main();assert(retained_fence&&retains==1&&!seed_calls&&!confirmations&&!service_acquires);retained_reset();
 for(unsigned cause=0;cause<=RISC_BOOT_DEEP_OTHER;cause++)for(unsigned present=0;present<2;present++){
  reset_case();boot_cause=cause;checkpoint_result=present?RISC_RETAINED_WAKE_OK:RISC_RETAINED_WAKE_ABSENT;
  app_main();check_clean();assert(first_seen&&first_at==95&&first_frames==1&&input_at==95&&input_stages==1);assert(service_acquires==4&&confirmations==1&&promotions==1&&stage_calls==1);
  assert(seed_calls==1);assert(face.time_valid);
  assert(rtc_acquires==1&&alarm_acquires==1);
  check_boot_stages();
 }
 reset_case();display_load_cost=275;sleep_setting_cost=900;app_main();check_clean();check_boot_stages();
 assert(first_at==370&&input_at==1270&&wake_stage_times[stage_index("display-end")]-wake_stage_times[stage_index("display-begin")]==275);
 assert(wake_stage_times[stage_index("first-frame")]==370&&wake_stage_times[stage_index("sleep-settings-end")]==1270);
 assert(wake_stage_times[stage_index("first-frame")]==wake_stage_times[stage_index("unblank-end")]);
 reset_case();boot_cause=RISC_BOOT_DEEP_GPIO;alarm_load_cost=700;app_main();check_clean();check_boot_stages();
 assert(first_at==95&&input_at==95&&rtc_acquires==1&&alarm_acquires==1&&radio_at==890);
 assert(wake_stage_times[stage_index("alarm-end")]-wake_stage_times[stage_index("alarm-begin")]==700);
 reset_case();fail_marker_sample=true;app_main();check_clean();
 assert(first_seen&&first_at==95&&confirmations==1&&stage_count("display-begin")==1&&!stage_count("display-end"));
 static const char *const failed_caps[]={RISC_REALTIME_CONTROL_CAPABILITY,"display.output","board.battery",ALARM_SERVICE_CAPABILITY,"input.touch.raw"};
 static const char *const failed_stages[]={"runtime-grants","display","battery","alarm","touch"};
 for(unsigned i=0;i<sizeof(failed_caps)/sizeof(*failed_caps);i++) {
  reset_case();fail_capability=failed_caps[i];app_main();check_clean();
  char begin[32],end[32];snprintf(begin,sizeof(begin),"%s-begin",failed_stages[i]);snprintf(end,sizeof(end),"%s-end",failed_stages[i]);
  assert(stage_count(begin)==1&&!stage_count(end)&&!service_acquires&&!confirmations);
  assert(first_seen==!strcmp(failed_caps[i],ALARM_SERVICE_CAPABILITY));
 }
 reset_case();fail_frame_acquire=true;app_main();check_clean();
 assert(stage_count("render-begin")==1&&!stage_count("render-end")&&!stage_count("transfer-begin")&&!first_seen);
 reset_case();fail_unblank=true;app_main();check_clean();
 assert(stage_count("transfer-end")==1&&stage_count("unblank-begin")==1&&!stage_count("unblank-end")&&!first_seen&&!hardware_brightness);
 reset_case();early_launch=true;app_main();check_clean();assert(first_seen&&launches==1&&!service_acquires&&!confirmations);
 reset_case();swipe_during_frame=true;app_main();check_clean();assert(swipe_latched&&launches==1&&!service_acquires&&!confirmations&&clock_ms==190);
 reset_case();scenario=17;saved_face=true;memcpy(saved_blob,(uint8_t[]){0x46,1,1,1^0xa5},4);quick_saved[0]=true;quick_values[0]=60;app_main();check_clean();assert(first_seen&&picker.selected==1&&face.hour_24&&hardware_brightness==60);
 reset_case();unset_time=true;native_time.validity=RISC_REALTIME_UNSET;native_time.epoch_seconds=0;app_main();check_clean();assert(first_seen&&!face.time_valid&&!seed_calls);
 reset_case();alarm_view.state=ALARM_STATE_ALERT;alarm_view.occurrence.generation=1;app_main();check_clean();assert(alarm_frames&&first_seen&&first_at==95&&service_acquires==4);
 reset_case();boot_cause=RISC_BOOT_DEEP_GPIO;alarm_load_cost=700;alarm_view.state=ALARM_STATE_ALERT;alarm_view.occurrence.generation=1;
 app_main();check_clean();assert(first_at==95&&input_at==95&&alarm_frames&&rtc_acquires==1&&alarm_acquires==1&&!alarm_view.occurrence.generation);
 assert(stage_index("first-input-poll")<stage_index("alarm-begin")&&stage_index("reconcile-end")<stage_index("radios-begin"));
 reset_case();boot_cause=RISC_BOOT_DEEP_GPIO;alarm_load_cost=700;crown_before_alarm=true;
 alarm_view.state=ALARM_STATE_ALERT;alarm_view.occurrence.generation=1;
 app_main();check_clean();assert(first_at==95&&input_at==95&&prealarm_crown_events==1&&alarm_frames&&!sleeps&&confirmations==1);
 reset_case();boot_cause=RISC_BOOT_DEEP_GPIO;unset_time=true;native_time.validity=RISC_REALTIME_UNSET;native_time.epoch_seconds=0;
 app_main();check_clean();assert(first_seen&&!face.time_valid&&rtc_acquires==1&&!stage_count("rtc-deferred"));
 reset_case();fail_display=true;app_main();check_clean();assert(!first_seen&&!service_acquires&&!confirmations);
 assert(stage_count("transfer-begin")==1&&!stage_count("transfer-end")&&!stage_count("unblank-begin"));
 for(unsigned fail=3;fail<=4;fail++){reset_case();fail_service=fail;app_main();check_clean();assert(first_seen&&service_acquires==fail&&!confirmations);}
 reset_case();contexts_enabled=true;requested_wakes=2;app_main();check_clean();assert(seed_calls==3&&wake_count==2&&soft_frames==2&&soft_latency==95&&stage_calls==3&&input_stages==3&&broadcast_starts==3&&contexts_starts==3);
 assert(stage_count("first-frame")==1&&stage_count("render-begin")==3&&stage_count("transfer-end")==3&&stage_count("unblank-end")==3);
 /* Both acquisition refusals must preserve the selected face outside its
  * explicit error strip, finish the redraw before unblank, survive retries,
  * and clear the error completely after the next successful sleep/wake. */
 for(unsigned failure=1;failure<=2;failure++)for(unsigned selected=0;selected<WATCH_FACE_COUNT;selected++){
  reset_case();fail_sleep_acquire=failure;requested_wakes=3;contexts_enabled=true;
  saved_face=true;memcpy(saved_blob,(uint8_t[]){0x46,1,(uint8_t)selected,(uint8_t)(selected^0xa5)},4);
  app_main();check_clean();assert(picker.selected==selected&&first_at==95);
  assert(refused_cycles==2&&refused_restores==2&&sleep_acquire_errors==2&&clean_refusal_frames>=2);
  assert(sleeps==1&&wake_count==1&&soft_frames==1&&soft_latency==95&&!sleep_status[0]);
  assert(stage_calls==4&&input_stages==4&&broadcast_starts==4&&contexts_starts==4);
 }
 check_refusal_diagnostics();
 reset_case();contexts_enabled=true;early_sleep=true;requested_wakes=1;app_main();check_clean();assert(wake_count==1&&soft_frames==1&&stage_calls==1&&broadcast_starts==1&&contexts_starts==1&&confirmations==1);
 reset_case();low_percent=5;contexts_enabled=true;app_main();check_clean();assert(first_at==95&&input_at==95&&radio_at==190&&clock_quick.brightness==15&&hardware_brightness==15&&!clock_radios.flags&&low_writes[0]==1);
 reset_case();low_on_wake=true;contexts_enabled=true;requested_wakes=1;app_main();check_clean();assert(wake_count==1&&soft_latency==95&&resume_input_at==wake_began+95&&radio_at==resume_input_at+95&&clock_quick.brightness==15&&!clock_radios.flags&&low_writes[0]==1);
 reset_case();alarm_on_wake=true;requested_wakes=1;app_main();check_clean();assert(wake_count==1&&alarm_frames&&soft_latency>95&&soft_frames==1);
 for(unsigned variant=0;variant<4;variant++){
  reset_case();contexts_enabled=true;
  const uint8_t modes[]={PORTABLE_RADIO_WIFI,PORTABLE_RADIO_BLUETOOTH,PORTABLE_RADIO_AIRPLANE|PORTABLE_RADIO_PREVIOUS_BLUETOOTH,0};
  saved_radio(modes[variant]);if(variant==3){radio_bytes[3]^=1;ble_state=1;}
  app_main();check_clean();assert(confirmations==1&&first_at==95&&input_at==95);
  assert(ble_state==(variant==1));assert(clock_quick.ui.radios_valid==(variant!=3));assert(!clock_quick.ui.radios_valid||clock_radios.flags==modes[variant]);
 }
 for(unsigned fail=1;fail<=2;fail++){reset_case();fail_service=fail;app_main();check_clean();assert(first_seen&&!clock_quick.ui.radios_valid&&confirmations==1);}
 reset_case();saved_radio(PORTABLE_RADIO_BLUETOOTH);fail_ble_enable=true;app_main();assert(first_seen&&retained_fence&&retains&&!confirmations&&native_clock.halted&&radio_apply_count==1);retained_reset();
 reset_case();requested_wakes=1;fail_ble_enable=true;app_main();assert(first_seen&&retained_fence&&retains&&!wake_count&&confirmations==1&&native_clock.halted&&radio_apply_count==1);retained_reset();
 reset_case();contexts_enabled=true;requested_wakes=1;fail_broadcast_restart=true;app_main();assert(first_seen&&retained_fence&&retains&&wake_count==1&&confirmations==1&&clock_contexts.api);retained_reset();
 reset_case();contexts_enabled=expect_context_handoff=true;contexts_view.export_pending=CONTEXTS_RADIO;app_main();check_clean();assert(queued_context_handoff&&launches==1&&!confirmations&&clock_contexts_handoff);
 reset_case();fail_context_pause=true;app_main();assert(first_seen&&retains&&!confirmations&&clock_contexts_uncertain);
 /* Terminal retained fixture reset is outside that invocation. */
 retained_reset();
 reset_case();fail_release=true;app_main();assert(first_seen&&retains&&confirmations==1);retained_reset();
 puts("Fast Watch Clock: production Points/motion/alarm-resume feature paths; 10 cold/deep variants; exact first frame/input; mid-frame navigation; cold/light low-battery; phased service starts; radio policy/failure variants; early/repeated light wake; due alarms; terminal retain fences PASS");
 puts("Modeled cost only: 95 ms first Clock frame and input, four 700 ms service acquisitions plus 400 ms service starts deferred; 95 ms light-resume frame without an alarm; no physical timing claim.");
 puts("Boot/wake stage timing: ordered essential grants, settings, alarm/touch/reconciliation, render/transfer/unblank; first-frame precedes sleep settings; failure markers stop at failed boundary; light logs bounded per wake PASS");
 puts("Minimal first-frame closure: valid deep native time defers RTC then reconciles after first input; alarm/output admission follows first frame/input and precedes handoff/radios; 700 ms modeled load deferred; deep due alarms and stale crown cancellation PASS");
 puts("Sleep refusal: both acquire boundaries, every face unchanged outside explicit error strip, completed redraw before unblank, repeated retry/cleanup, success clears error, and exact stage/signed-detail diagnostics PASS");
 return 0;
}
