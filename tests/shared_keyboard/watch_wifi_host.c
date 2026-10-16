/* Actual production Watch defines, controller and adapter; copied providers only.
 * The shared fixture supplies deterministic display, storage, radio and alarm
 * boundaries. Local navigation/sleep are host doubles, never target inputs. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
/* The legacy fixture contains a visual-output-only test, unused here. Watch's
 * real alarm header is force-included and remains the selected production ABI. */
typedef struct { alarm_service_v1 service; uint32_t output_modes; } alarm_service_outputs_v1;
#undef PORTABLE_WIFI_INSTANCE
#undef PORTABLE_WIFI_SETTINGS_APP
#undef PORTABLE_ALARM_CLIENT
#undef PORTABLE_APP_SLEEP_LOCAL
#undef PORTABLE_INPUT_NAVIGATION
#define main watch_unused_legacy_main
#include "portable_wifi_test.c"
#undef main

static unsigned text_opens,text_closes,text_close_wait,grant_serial;
static bool text_live,text_refused,text_close_failed;
static risc_text_entry_request_v1 text_request;
static risc_text_entry_state_v1 text_result;
static int32_t text_open(void*c,const risc_text_entry_request_v1*q,uint64_t*out) {
 (void)c;assert(!surface.frame&&!sub_count&&!text_live);
 assert(portable_paper_frame_idle());
#ifdef PORTABLE_RASTER_SNAPSHOT
 assert(!raster_recording&&!raster_sealed&&!raster_commands&&!raster_offscreen);
#endif
 if(text_refused){*out=0;return RISC_TEXT_ENTRY_BUSY;}
 text_request=*q;text_live=true;++text_opens;*out=77;return RISC_TEXT_ENTRY_OK;
}
static int32_t text_poll(void*c,uint64_t id,risc_text_entry_state_v1*out) {
 (void)c;assert(text_live&&id==77&&!surface.frame&&!sub_count);*out=text_result;return RISC_TEXT_ENTRY_OK;
}
static int32_t text_close(void*c,uint64_t id) {
 (void)c;assert(text_live&&id==77&&!surface.frame&&!sub_count);++text_closes;
 if(text_close_failed)return RISC_TEXT_ENTRY_RETAINED;
 if(text_close_wait){--text_close_wait;return RISC_TEXT_ENTRY_AGAIN;}
 text_live=false;return RISC_TEXT_ENTRY_OK;
}
static risc_text_entry_api_v1_masked texts={{{1,sizeof(texts),NULL,text_open,text_poll,text_close},RISC_TEXT_ENTRY_HOME_REASON_TAG,RISC_TEXT_ENTRY_HOME_REASON_VERSION},RISC_TEXT_ENTRY_MASKED_TAG,RISC_TEXT_ENTRY_MASKED_VERSION};
static const risc_text_entry_api_v1 *offered_text=&texts.base.base;
static bool retained;
static bool retain_runtime(void){retained=true;return true;}
static bool bc_pause(void*c){(void)c;return true;}
static bool bc_step(void*c,bool a,const telemetry_broadcast_policy_v1*p){(void)c;(void)a;(void)p;return true;}
static bool bc_status(void*c,telemetry_broadcast_status_v1*out){(void)c;*out=(telemetry_broadcast_status_v1){.struct_size=sizeof(*out),.state=TELEMETRY_BROADCAST_OFF};return true;}
static int32_t bc_enum(void*c,uint32_t i,risc_telemetry_field_v1*out){(void)c;(void)i;(void)out;return 0;}
static int32_t bc_read(void*c,uint32_t i,int32_t*out){(void)c;(void)i;(void)out;return 0;}
static const telemetry_broadcast_v1 bc_api={1,sizeof(bc_api),NULL,bc_step,bc_pause,bc_status,bc_enum,bc_read};
static uint8_t ble_enabled;
static bool ble_set(void*c,bool enabled){(void)c;ble_enabled=enabled;return true;}
static bool ble_status(void*c,uint8_t*out){(void)c;*out=ble_enabled;return true;}
static const portable_bluetooth_control_v1 ble_api={.api_version=1,.struct_size=sizeof(ble_api),.set_enabled=ble_set,.status=ble_status};
static bool battery_read(void*c,risc_battery_sample_v1*out){(void)c;*out=(risc_battery_sample_v1){.millivolts=4000,.percent=80};return true;}
static const risc_battery_gauge_api_v1 battery_api={1,sizeof(battery_api),NULL,battery_read};
static bool rtc_read(void*c,twatch_rtc_time_v1*out){(void)c;*out=(twatch_rtc_time_v1){2026,10,12,1,16,0,0};return true;}
static const twatch_rtc_api_v1 rtc_api={.api_version=2,.struct_size=sizeof(rtc_api),.read=rtc_read};
static bool host_acquire(const char*n,uint32_t v,uint64_t id,risc_runtime_capability_v1*g) {
 if(!strcmp(n,RISC_TEXT_ENTRY_CAPABILITY)){assert(v==1&&!id);g->api=offered_text;++grant_count;}
 else if(!strcmp(n,TELEMETRY_BROADCAST_CAPABILITY)){g->api=&bc_api;++grant_count;}
 else if(!strcmp(n,"bluetooth.hci")){assert(id==16);g->api=&ble_api;++grant_count;}
 else if(!strcmp(n,"board.battery")){g->api=&battery_api;++grant_count;}
 else if(!strcmp(n,"rtc.clock")){g->api=&rtc_api;++grant_count;}
 else if(!fake_acquire(n,v,id,g))return false;
 g->struct_size=sizeof(*g);g->slot=++grant_serial;g->generation=1;return true;
}
static bool host_release(risc_runtime_capability_v1*g) {
 if(g->api==offered_text)assert(!text_live);
 if(!fake_release(g))return false;
 *g=(risc_runtime_capability_v1){.struct_size=sizeof(*g)};return true;
}
static risc_input_navigation_frame_v1 local_frame;
static bool local_poll_fail;
static unsigned local_polls,local_resets;
static bool local_nav_poll(void*c,risc_input_navigation_frame_v1*out){(void)c;++local_polls;*out=local_frame;return !local_poll_fail;}
static bool local_nav_reset(void*c){(void)c;++local_resets;local_frame=(risc_input_navigation_frame_v1){0};return true;}
static bool local_nav_foreground(void*c,const risc_input_foreground_v1*a,size_t n){(void)a;(void)n;return local_nav_reset(c);}
static const risc_input_navigation_api_v1 watch_nav_api={1,sizeof(watch_nav_api),NULL,local_nav_poll,local_nav_foreground,local_nav_reset};
const risc_input_navigation_api_v1 *portable_input_navigation_open(const risc_runtime_api_v1*r){(void)r;return &watch_nav_api;}
void portable_input_navigation_close(const risc_runtime_api_v1*r){(void)r;}
static void start_watch(void) {
 runtime_api=(risc_runtime_api_v1){.api_version=1,.struct_size=sizeof(runtime_api),.health=fake_health,.yield_ms=fake_yield,.diagnostic=fake_diag,.request_launch=fake_launch,.acquire=host_acquire,.release=host_release,.retain_invocation=retain_runtime};
 radio_api=(wifi_api_v1){.api_version=1,.struct_size=sizeof(radio_api),.connect=fake_connect,.disconnect=fake_disconnect_legacy,.status=fake_status,.rssi=fake_rssi,.addresses=fake_addresses,.scan_start=fake_scan_start,.scan_poll=fake_scan_poll,.scan_cancel=fake_scan_cancel,.disconnect_checked=fake_disconnect};
 fake_scan=(garden_radio_scan_result_v1){.struct_size=sizeof(fake_scan),.state=GARDEN_RADIO_SCAN_RUNNING};
 assert(app_module_init()==0);assert(wifi_open());draft();
 (void)pqa_input(&quick.ui,ticks,true,0,0,0,0,true);
 assert(portable_wifi_idle_ready());
}
static void text_done(unsigned state,const char*value,unsigned flags) {
 text_result=(risc_text_entry_state_v1){.struct_size=sizeof(text_result),.revision=1,.state=state,.flags=flags};
 strcpy(text_result.text,value);wifi_text_step();
}
int main(int argc,char**argv) {
 assert(argc==2);unsigned which=(unsigned)atoi(argv[1]);start_watch();
 if(which==0){
  render();assert(portable_paper_frame_drain());
  wifi_edit(WP_PASSWORD);assert(wifi_text_active&&text_live&&text_opens==1&&(text_request.reserved&RISC_TEXT_ENTRY_REQUEST_MASKED));
  unsigned before=writes;text_close_wait=2;text_done(RISC_TEXT_ENTRY_ACCEPTED,"new-synthetic-password",0);
  assert(wifi_text_active&&!strcmp(credentials.password,"testpass123")&&writes==before);
  wifi_text_step();assert(wifi_text_active);wifi_text_step();
  assert(!wifi_text_active&&!text_live&&!strcmp(credentials.password,"new-synthetic-password")&&draft_dirty&&writes==before);
 }else if(which==1){
  wifi_edit(WP_SSID);assert(!(text_request.reserved&RISC_TEXT_ENTRY_REQUEST_MASKED));text_done(RISC_TEXT_ENTRY_ACCEPTED,"Updated network",0);
  assert(!strcmp(credentials.ssid,"Updated network")&&!text_live&&!writes);
 }else if(which==2){
  wifi_edit(WP_PASSWORD);text_done(RISC_TEXT_ENTRY_CANCELLED,"discarded-secret",0);
  assert(!strcmp(credentials.password,"testpass123")&&!text_live&&!writes);
 }else if(which==3){
  wifi_edit(WP_PASSWORD);text_done(RISC_TEXT_ENTRY_CANCELLED,"discarded-secret",RISC_TEXT_ENTRY_HOME_CANCEL);
  assert(wifi_home_return&&!strcmp(credentials.password,"testpass123")&&!writes&&!text_live);
 }else if(which==4){
  risc_text_entry_api_v1 old=texts.base.base;old.struct_size=sizeof(old);offered_text=&old;
  wifi_edit(WP_PASSWORD);assert(!wifi_text_active&&!text_opens&&!strcmp(credentials.password,"testpass123"));
 }else if(which==5){
  text_refused=true;wifi_edit(WP_PASSWORD);assert(!text_live&&!wifi_text_active&&!strcmp(credentials.password,"testpass123")&&sub_count==1&&!writes);
 }else if(which==6){
  for(unsigned i=0;i<10;i++){(void)pqa_input(&quick.ui,ticks,true,0,0,0,0,true);wifi_edit(WP_PASSWORD);assert(text_live);text_done(RISC_TEXT_ENTRY_CANCELLED,"",0);assert(!text_live&&sub_count==1);}
  assert(text_opens==10&&text_closes==10);
 }else if(which==7){
  wifi_edit(WP_PASSWORD);text_close_wait=3;assert(!portable_wifi_close());
  text_done(RISC_TEXT_ENTRY_CANCELLED,"",0);
  for(unsigned i=0;i<3;i++)wifi_text_step();
  assert(!wifi_text_active&&!text_live&&portable_wifi_close()&&!opened);
 }else if(which==8){
  wifi_edit(WP_PASSWORD);text_close_failed=true;text_done(RISC_TEXT_ENTRY_ACCEPTED,"never-committed",0);
  assert(retained&&portable_text_adapter_retained()&&text_live&&!strcmp(credentials.password,"testpass123"));
  unsigned live=grant_count;app_module_fini();assert(grant_count==live&&text_live&&!writes);
  puts("Watch masked keyboard terminal cleanup retained PASS");return 0;
 }else if(which==9){
  scanning=true;assert(!portable_wifi_idle_ready());scanning=false;
  scan_owned=true;assert(!portable_wifi_idle_ready());scan_owned=false;
  joining=true;assert(!portable_wifi_idle_ready());joining=false;
  cleanup_pending=true;assert(!portable_wifi_idle_ready());cleanup_pending=false;
  assert(portable_wifi_idle_ready());
 }else if(which==10||which==11){
  assert(portable_paper_frame_ready());clear_color(0x1357);fill(0,0,240,240,0x2468);
  if(which==11){present(false);assert(raster_sealed);}else assert(raster_recording);
  wifi_edit(WP_PASSWORD);assert(text_live&&wifi_text_active);
  unsigned before=presents;assert(paper_present_progress());assert(presents==before);
  text_done(RISC_TEXT_ENTRY_CANCELLED,"",0);assert(!text_live);
 }else if(which==12){
  assert(portable_wifi_close());
  held_touch(poll_count+20,60,130);
  text_result=(risc_text_entry_state_v1){.struct_size=sizeof(text_result),.revision=1,.state=RISC_TEXT_ENTRY_CANCELLED,.flags=RISC_TEXT_ENTRY_HOME_CANCEL};
  app_main();
  assert(text_opens==1&&wifi_home_return&&!opened&&!text_live&&!launches&&!writes&&presents);
 }else if(which==13){
  wifi_edit(WP_PASSWORD);assert(text_live);
  local_frame=(risc_input_navigation_frame_v1){.buttons=RISC_NAV_BACK,.pressed=RISC_NAV_BACK};
  text_done(RISC_TEXT_ENTRY_EDITING,"testpass123",0);assert(text_live&&wifi_text_active);
  local_frame=(risc_input_navigation_frame_v1){0};wifi_text_step();assert(text_live);
  local_frame=(risc_input_navigation_frame_v1){.pressed=RISC_NAV_BACK,.released=RISC_NAV_BACK};wifi_text_step();
  assert(!text_live&&!wifi_text_active&&!strcmp(credentials.password,"testpass123")&&!writes&&!launches);
  (void)pqa_input(&quick.ui,ticks,true,0,0,0,0,true);wifi_edit(WP_PASSWORD);assert(text_live);
  text_done(RISC_TEXT_ENTRY_EDITING,"testpass123",0);assert(text_live&&wifi_text_active);
  text_done(RISC_TEXT_ENTRY_CANCELLED,"",0);assert(!text_live&&local_resets>=6&&local_polls>=4);
 }else if(which==14){
  wifi_edit(WP_PASSWORD);local_poll_fail=true;text_done(RISC_TEXT_ENTRY_EDITING,"testpass123",0);
  assert(retained&&portable_text_adapter_retained()&&text_live&&!writes);
  unsigned before=local_polls;wifi_text_step();app_module_fini();assert(local_polls==before);
  puts("Watch local Back poll failure retained PASS");return 0;
 }else assert(!"Unknown case");
 assert(!text_live&&!retained);finish();
 printf("Watch actual-profile masked keyboard case %u PASS\n",which);return 0;
}
