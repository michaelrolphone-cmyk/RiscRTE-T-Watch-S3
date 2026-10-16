/* Full production Clock / FAST_WAKE gesture regression.
 * Device boundaries reuse quick_clock_test.c; the modeled startup fixture is
 * derived from fast_wake_clock_test.c. Gesture input is only real raw snapshots.
 * No case sets launcher_swipe_pending to synthesize successful navigation.
 * The renderer is real; elapsed time is injected at its existing checkpoints.
 * WATCH_RASTER_EXPECT_LOSS permits reference-tree diagnosis without journal APIs.
 */
/* Production Clock and renderer; fake device/API boundaries and explicit costs.
 * No host wall-clock measurement is reported as ESP32 hardware timing. */
#define nova_watch_face_render probe_render
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
#include <tests/quick_clock_test.c>

#undef main

static unsigned probe_trajectory, probe_began, probe_quick_open, probe_duration, probe_offset;
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
static bool crown_before_alarm;
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
static void check_io(void){assert(!retained_fence);}
static risc_realtime_snapshot_v1 native_time;
static alarm_status_v1 alarm_view;
static contexts_status_v1 contexts_view;
static int32_t native_read(void*c,risc_realtime_snapshot_v1*out){check_io();(void)c;*out=native_time;return 0;}
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

 }
 if(strstr(s,"stage=first-input-poll")){input_at=clock_ms;input_stages++;assert(touch.subscription&&polls);if(wake_count)resume_input_at=clock_ms;}
 if(strstr(s,"stage=light-resume")){wake_began=clock_ms;assert(!clock_quick.ui.radios_valid&&!clock_radios.valid&&!clock_radios.available);assert(!clock_broadcast_started&&!clock_contexts_started);}
 if(strstr(s,"stage=light-frame")){soft_frames++;soft_latency=clock_ms-wake_began;assert(!pending&&!owned&&hardware_brightness==clock_quick.brightness);
  assert(!sleep_status[0]);if(refused_restores)check_refusal_pixels();
 }
 if(strstr(s,"stage=radios-begin")){radio_at=clock_ms;assert(input_stages>0);if(wake_count)assert(resume_input_at>=wake_began);assert(frame_at>=(wake_count?wake_began:first_at));}
 if(strstr(s,"stage=broadcast-begin"))broadcast_at=clock_ms;
 if(strstr(s,"stage=contexts-begin"))contexts_at=clock_ms;
 if(strstr(s,"stage=services-ready")){stage_calls++;if(wake_count+refused_cycles==requested_wakes&&!early_launch && !probe_began)probe_began=clock_ms;}
 return true;
}
static bool fast_status(void*c,uint64_t token,risc_display_present_status_v1*out){
 check_io();(void)c;assert(token==submitted&&pending);

 if(clock_ms-frame_started<transfer_cost){out->state=RISC_DISPLAY_PRESENT_ACTIVE;return true;}
 pending=false;if(probe_began && clock_ms-probe_began>=1000)ended=true;out->state=fail_display?RISC_DISPLAY_PRESENT_FAILED:RISC_DISPLAY_PRESENT_COMPLETE;
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
static bool fast_rtc(void*c,twatch_rtc_time_v1*out){if(unset_time){memset(out,0,sizeof(*out));return true;}return rtc_read(c,out);}
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
static bool fast_snapshot(void*c,risc_touch_snapshot_v1*out){check_io();(void)c;*out=(risc_touch_snapshot_v1){.width=240,.height=240};
 if(probe_began && clock_ms>=probe_began+probe_offset && clock_ms<probe_began+probe_offset+probe_duration) {
 unsigned age=clock_ms-probe_began-probe_offset; unsigned x=120,y=120;
 if(probe_trajectory==0)x=200-age*160/probe_duration;
 else {y=10+age*225/probe_duration;x=120;}
 out->contact_count=1;out->contacts[0]=(risc_touch_contact_v1){1,0,x,y};
 } if(clock_quick.ui.target_q8==PQA_OPEN_Q8)probe_quick_open=1;
 return true;}
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
 crown_before_alarm=false;prealarm_crown_events=0;
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
#undef nova_watch_face_render
extern bool nova_watch_face_render(risc_display_surface_v1 *,const nova_watch_state *,unsigned);
static bool (*probe_saved_capture)(void *);
static unsigned raster_delay, raster_cost, raster_probes, raster_at, raster_steps, max_poll_gap, last_poll_at;
static bool probe_checkpoint(void *c){ (void)c; raster_steps++; clock_ms+=raster_delay;return !probe_saved_capture || probe_saved_capture(c); }
bool probe_render(risc_display_surface_v1 *s,const nova_watch_state *f,unsigned n) {
 if(probe_began && s->pixels==pixels && clock_deferred_phase==4) {
  nova_watch_state clone=*f;probe_saved_capture=f->capture_audio;clone.capture_audio=probe_checkpoint;clone.capture_context=NULL;
  unsigned began=clock_ms, polls_before=polls;raster_steps=0;
  bool result=nova_watch_face_render(s,&clone,n);
  if(clock_ms-began>raster_cost)raster_cost=clock_ms-began;
  raster_probes+=polls-polls_before; raster_at=began;return result;
 } return nova_watch_face_render(s,f,n);
}
static bool probe_poll(void *c,size_t n) { if(probe_began && last_poll_at>=probe_began && clock_ms-last_poll_at>max_poll_gap)max_poll_gap=clock_ms-last_poll_at;last_poll_at=clock_ms;return poll(c,n);}
static void run_matrix(void) {
 unsigned recognized=0,total=0;
 static const unsigned durations[]={80,160},delays[]={0,1,2,3,5};
 for(unsigned wake=0;wake<2;wake++)for(unsigned d=0;d<2;d++)for(unsigned cost=0;cost<5;cost++)for(probe_trajectory=0;probe_trajectory<2;probe_trajectory++) {
  reset_case();probe_began=probe_quick_open=0;probe_duration=durations[d];probe_offset=20;raster_delay=delays[cost];
  raster_cost=raster_probes=max_poll_gap=last_poll_at=0;requested_wakes=wake;ta.poll=probe_poll;
  app_main();check_clean();
  bool correct=probe_trajectory?(probe_quick_open&&launches==0):(launches==1);
  if(!raster_delay){assert(correct);}
  recognized+=correct;total++;
#ifndef WATCH_RASTER_EXPECT_LOSS
  assert(correct);
#endif
  printf("{\"wake\":%u,\"duration_ms\":%u,\"gesture\":\"%s\",\"checkpoint_cost_ms\":%u,\"raster_cost_ms\":%u,\"raster_polls\":%u,\"max_settled_poll_gap_ms\":%u,\"launches\":%u,\"quick_open\":%u}\n",wake,probe_duration,probe_trajectory?"quick-down":"launcher-left",raster_delay,raster_cost,raster_probes,max_poll_gap,launches,probe_quick_open);
 }
 assert(total==40);
#ifdef WATCH_RASTER_EXPECT_LOSS
 assert(recognized<total);
#else
 assert(recognized==total);
#endif
 printf("MATRIX SUMMARY %u/%u recognized; modeled work only, no hardware timing claim\n",recognized,total);
}

#ifndef WATCH_RASTER_EXPECT_LOSS
/* Candidate-only boundary tests. No hardware timing claim. */
static risc_touch_snapshot_v1 boundary_state;
static bool boundary_snapshot_ok,boundary_poll_ok;
static int boundary_next_result;
static unsigned boundary_cases;
static bool boundary_snapshot(void*c,risc_touch_snapshot_v1*out){(void)c;*out=boundary_state;return boundary_snapshot_ok;}
static bool boundary_poll(void*c,size_t n){(void)c;assert(n==1);return boundary_poll_ok;}
static int32_t boundary_next(void*c,uint64_t s,risc_touch_event_v1*out){(void)c;(void)s;(void)out;return boundary_next_result;}
static void boundary_reset(void) {
 reset_case();rt=&fast_runtime.prefix;native_clock=(watch_clock_runtime){0};
 clock_contexts=(portable_contexts_client){0};clock_contexts_uncertain=false;clock_alarm_modal=false;
 pqa_session_init(&clock_quick);picker=(watch_face_picker){0};picker_scratch=NULL;
 launcher_swipe_pending=launcher_activity_pending=picker_open_pending=picker_select_pending=false;
 launcher_sampled_at=0;clock_raster_count=0;clock_raster_overflow=clock_raster_activity=false;
 clock_rendering=true;clock_display_settled=false;held=1;
 touch=(watch_launcher_touch){.api=&ta,.subscription=1};
 ta.snapshot=boundary_snapshot;ta.poll=boundary_poll;ta.next=boundary_next;
 boundary_snapshot_ok=boundary_poll_ok=true;boundary_next_result=0;
 boundary_state=(risc_touch_snapshot_v1){.width=240,.height=240};
}
static void boundary_capture(unsigned ms,unsigned count,unsigned id,unsigned x,unsigned y) {
 clock_ms=ms;boundary_state.contact_count=count;boundary_state.contacts[0]=(risc_touch_contact_v1){id,0,x,y};
 watch_face_picker prior_picker=picker;pqa_session prior_quick=clock_quick;
 bool launch=launcher_swipe_pending,open=picker_open_pending,select=picker_select_pending;
 assert(clock_render_checkpoint(NULL));
 assert(!memcmp(&prior_picker,&picker,sizeof(picker)));assert(!memcmp(&prior_quick,&clock_quick,sizeof(clock_quick)));
 assert(launch==launcher_swipe_pending&&open==picker_open_pending&&select==picker_select_pending);
 assert(!launches&&!allocations); /* Raw capture cannot launch, allocate or mutate UI. */
}
static void boundary_direct(unsigned ms,unsigned count,unsigned id,unsigned x,unsigned y) {
 clock_ms=ms;boundary_state.contact_count=count;boundary_state.contacts[0]=(risc_touch_contact_v1){id,0,x,y};
 clock_rendering=false;sample_launcher_touch(ms,true);clock_rendering=true;
 assert(!launches&&!allocations);
}
static void boundary_flush(void){clock_rendering=false;held=0;clock_display_settled=true;clock_replay_raster_input();assert(!launches&&!allocations);clock_rendering=true;held=1;clock_display_settled=false;}
static void boundary_neutral(unsigned ms){boundary_capture(ms,0,0,0,0);boundary_capture(ms+8,0,0,0,0);}
static void boundary_idle(void){assert(!launcher_swipe_pending&&!picker_open_pending&&!picker_select_pending&&!picker.open&&!pqa_visible(&clock_quick.ui));}
static void boundary_done(const char *name){printf("BOUNDARY PASS %s\n",name);boundary_cases++;held=0;clock_rendering=false;}
static void run_boundaries(void){
 boundary_reset();boundary_neutral(8);boundary_capture(24,1,1,120,120);boundary_capture(80,0,0,0,0);boundary_flush();boundary_idle();boundary_done("tap-only remains inert");
 boundary_reset();boundary_neutral(8);for(unsigned ms=24;ms<=824;ms+=8)boundary_capture(ms,1,1,120,120);boundary_capture(832,0,0,0,0);boundary_flush();assert(picker.open&&picker_open_pending&&!picker_scratch&&!launcher_swipe_pending);boundary_done("800ms hold opens picker only after raster, with no allocation");
 for(unsigned fault=0;fault<6;fault++) {
  boundary_reset();boundary_neutral(8);boundary_capture(24,1,1,120,120);
  if(fault==0)boundary_poll_ok=false;
  if(fault==1)boundary_snapshot_ok=false;
  if(fault==2)boundary_next_result=-1;
  if(fault==3)boundary_state.width=239;
  boundary_capture(32,fault==4?2:1,fault==5?2:1,120,120);
  boundary_poll_ok=boundary_snapshot_ok=true;boundary_next_result=0;boundary_state.width=240;
  boundary_capture(40,1,fault==5?2:1,60,120);boundary_flush();boundary_idle();
  boundary_neutral(48);boundary_capture(64,1,3,120,120);boundary_capture(80,1,3,60,120);boundary_flush();assert(launcher_swipe_pending);
  const char *names[]={"poll failure cancels then fresh gesture recovers","snapshot failure cancels then recovers","queue GAP cancels then recovers","invalid geometry cancels then recovers","multitouch cancels then recovers","contact replacement cancels then recovers"};boundary_done(names[fault]);
 }
 boundary_reset();boundary_neutral(8);boundary_capture(24,1,1,200,120);boundary_capture(32,1,1,100,120);
 for(unsigned ms=40;ms<1200;ms+=8)boundary_capture(ms,1,1,100,120);
 assert(clock_raster_overflow);boundary_flush();boundary_idle();
 boundary_capture(1200,1,1,40,120);boundary_flush();boundary_idle();
 boundary_neutral(1208);boundary_capture(1224,1,2,120,120);boundary_capture(1240,1,2,60,120);boundary_flush();assert(launcher_swipe_pending);boundary_done("overflow discards queued swipe and requires fresh neutral");
 boundary_reset();boundary_neutral(8);boundary_capture(24,1,1,120,10);boundary_capture(40,1,1,120,120);boundary_capture(56,1,1,120,235);boundary_capture(64,0,0,0,0);boundary_capture(72,0,0,0,0);boundary_flush();assert(clock_quick.ui.target_q8==PQA_OPEN_Q8&&!launcher_swipe_pending);
 clock_quick.ui.position_q8=PQA_OPEN_Q8; /* Model fully settled previous frame. */
 boundary_capture(80,1,2,120,222);boundary_capture(96,1,2,120,100);boundary_capture(112,1,2,120,0);boundary_capture(120,0,0,0,0);boundary_capture(128,0,0,0,0);boundary_flush();assert(clock_quick.ui.target_q8==0&&!launcher_swipe_pending);
 clock_quick.ui.position_q8=0;
 boundary_capture(136,1,3,120,10);boundary_capture(152,1,3,120,120);boundary_capture(168,1,3,120,235);boundary_capture(176,0,0,0,0);boundary_flush();assert(clock_quick.ui.target_q8==PQA_OPEN_Q8&&!launcher_swipe_pending);boundary_done("consecutive quick-controls open close reopen");
 boundary_reset();boundary_neutral(8);boundary_capture(24,1,1,120,10);boundary_capture(40,1,1,180,10);boundary_flush();assert(launcher_swipe_pending&&!pqa_visible(&clock_quick.ui));boundary_done("horizontal top-edge gesture replays to launcher");
 boundary_reset();boundary_neutral(8);boundary_flush();boundary_direct(24,1,1,120,120);assert(picker.down);
 boundary_capture(32,1,1,80,120);boundary_capture(40,0,0,0,0);boundary_flush();assert(launcher_swipe_pending);boundary_done("launcher starts before raster and ends inside raster");
 boundary_reset();boundary_neutral(8);boundary_capture(24,1,1,120,120);boundary_flush();assert(picker.down&&!launcher_swipe_pending);
 boundary_direct(32,1,1,80,120);assert(launcher_swipe_pending);boundary_done("launcher starts inside raster and completes after raster");
 boundary_reset();boundary_neutral(8);boundary_flush();boundary_direct(24,1,1,120,10);
 boundary_capture(40,1,1,120,120);boundary_capture(56,1,1,120,235);boundary_capture(64,0,0,0,0);boundary_flush();assert(clock_quick.ui.target_q8==PQA_OPEN_Q8&&!launcher_swipe_pending);boundary_done("Quick starts before raster and releases inside raster");
 boundary_reset();boundary_neutral(8);boundary_capture(24,1,1,120,10);boundary_capture(40,1,1,120,120);boundary_capture(56,1,1,120,235);boundary_flush();assert(clock_quick.ui.gesture==PQA_PANEL_DRAG&&!launcher_swipe_pending);
 boundary_direct(64,0,0,0,0);assert(clock_quick.ui.target_q8==PQA_OPEN_Q8&&!launcher_swipe_pending);boundary_done("Quick starts inside raster and releases after raster");
 printf("BOUNDARY SUMMARY %u cases; exact capture/replay; no UI mutation during capture; no allocation or launch before settled handling\n",boundary_cases);
}

#endif
int main(void){run_matrix();
#ifndef WATCH_RASTER_EXPECT_LOSS
run_boundaries();
#endif
return 0;}
