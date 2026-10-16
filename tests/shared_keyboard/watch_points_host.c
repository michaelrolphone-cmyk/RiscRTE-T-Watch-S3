/* Audit-only host peripheral fixture. Normal app and adapter sources are compiled
 * independently and unmodified, using delivered UI deployment feature macros. */
#include "PortableApps.h"
#include "RiscDisplayOutputV1.h"
#include "RiscTouchV1.h"
#include "RiscBatteryGaugeV1.h"
#include "PortableRtcClock.h"
#include "RiscKeyValueV1.h"
#include "PortableNavigation.h"
#include "PortableAppSleep.h"
#include "PortableTextInputHandoff.h"
#include "AlarmServiceV1.h"
#include "PortableBluetoothControl.h"
#include "RiscPlatformClockV1.h"
#include "RiscTextEntryV1.h"
#include "RiscSceneV1.h"
#include "SceneProfileV1.h"
#include "PointsRecords.h"
static const risc_driver_v2 *scene_driver,*text_driver;
const risc_driver_v2 *points_scene_driver_get(uint32_t);
const risc_driver_v2 *points_text_driver_get(uint32_t);
const risc_driver_v2 *points_profile_driver_get(uint32_t);
#include "WifiApi.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
void app_main(void);int app_module_init(void);void app_module_fini(void);
static unsigned ticks,polls,grants,frames,subs,presents,text_grants,name_writes,point_writes,grant_serial;
static bool text_granted;
static char requests[8][POINTS_CUSTOM_NAME_MAX+1];
static uint8_t seed_points[POINTS_RECORD_SIZE],seed_meta[POINTS_RECORD_SIZE];
#ifdef RISC_RUNTIME_RETAIN_INVOCATION_V1_SIZE
static bool native_retained;
static unsigned retained_grants,retained_subs,retained_frames;
static bool fake_retain_invocation(void){native_retained=true;retained_grants=grants;retained_subs=subs;retained_frames=frames;return true;}
#endif
#ifdef POINTS_WATCH_RENDER
static bool runtime_lost;
#define CHECK_IO() assert(!runtime_lost&&!native_retained)
static bool loss_case(const char*name){const char*mode=getenv("POINTS_CASE");return mode&&!strcmp(mode,name);}
static const risc_text_entry_api_v1_home_reason text_proxy;
#else
#define CHECK_IO() ((void)0)
#endif
static bool is_text_api(const void*api){
#ifdef POINTS_WATCH_RENDER
 return api==&text_proxy;
#else
 return api==text_driver->capability;
#endif
}
/* One provider queue per active subscriber. App and modal subscriptions transfer
 * custody rather than overlap. Capture-only raster polls may enqueue reports;
 * they must never overwrite an edge or advance the gesture clock. */
#define TOUCH_QUEUE_CAPACITY 64u
static risc_touch_event_v1 touch_events[TOUCH_QUEUE_CAPACITY];
static unsigned touch_head,touch_count,touch_edges,action_cursor;
static uint64_t touch_sequence;
static bool touch_down;
static int touch_x,touch_y;
static unsigned next_action_at,host_session_frames,app_resume_frame;
static bool action_gate_wait;
static uint64_t grant_instances[8192];
static uint32_t navigation_pressed;
static unsigned stop_at=15000;
static unsigned radio_state,launches,radio_control_calls;static bool radio_owned;
#ifdef POINTS_PAPER_RENDER
#define PANEL_W 800
#define PANEL_H 480
#define TOUCH_W 480
#define TOUCH_H 800
#define PIXEL_FORMAT RISC_DISPLAY_FORMAT_MONO1
#define ROW_BYTES 100
#define STRIDE_BYTES 104
#else
#define PANEL_W 240
#define PANEL_H 240
#define TOUCH_W 240
#define TOUCH_H 240
#define PIXEL_FORMAT RISC_DISPLAY_FORMAT_RGB565
#define ROW_BYTES 480
#define STRIDE_BYTES 488
#endif
static unsigned char pixels[PANEL_H*STRIDE_BYTES];
static unsigned app_frames,host_frames,present_pending,rapid_edges,rapid_frame;
#ifdef POINTS_PAPER_RENDER
static bool physical_black(unsigned x,unsigned y){
 unsigned px=y,py=PANEL_H-1-x;
 return !!(pixels[py*STRIDE_BYTES+px/8]&(0x80u>>(px%8)));
}
#endif
static const char *directory;
static struct {unsigned delay_ms;char gate[16],kind[16];int x,y;} actions[256];static unsigned action_count;
static struct {char key[16];unsigned char bytes[64];uint32_t size;} cells[32];
static void save_frame(void) {
 char path[1024];snprintf(path,sizeof(path),"%s/frame-%03u.ppm",directory,presents);
 FILE*f=fopen(path,"wb");assert(f);fprintf(f,"P6\n%u %u\n255\n",TOUCH_W,TOUCH_H);
 for(unsigned y=0;y<TOUCH_H;y++)for(unsigned x=0;x<TOUCH_W;x++){
#ifdef POINTS_PAPER_RENDER
  /* Read both presenters in the installed app's physical orientation. */
  unsigned px=y,py=PANEL_H-1-x;unsigned char v=(pixels[py*STRIDE_BYTES+px/8]&(0x80u>>(px%8)))?0:255;
  unsigned char rgb[]={v,v,v};
#else
  uint16_t v;memcpy(&v,pixels+y*STRIDE_BYTES+x*2,2);unsigned char rgb[]={(v>>11)*255/31,((v>>5)&63)*255/63,(v&31)*255/31};
#endif
  assert(fwrite(rgb,1,3,f)==3);
 }
 for(unsigned y=0;y<PANEL_H;y++)for(unsigned x=ROW_BYTES;x<STRIDE_BYTES;x++)assert(pixels[y*STRIDE_BYTES+x]==0xa5);
 assert(!fclose(f));
}
static bool fake_health(risc_runtime_health_v1*h){CHECK_IO();h->uptime_ms=ticks;
#ifdef PORTABLE_NATIVE_CUSTODY_FENCE
 return true;
#else
 return ticks<stop_at;
#endif
}
static void fake_yield(uint32_t n){CHECK_IO();ticks+=n;assert(ticks<60000&&"script failed to complete within simulated deadline");}
static bool fake_diag(const char*s){CHECK_IO();fprintf(stderr,"%s\n",s);return true;}
static bool fake_launch(const char*s){CHECK_IO();assert(!radio_owned&&!text_granted);assert(!strcmp(s,"springboard.elf"));launches++;printf("launch=%s\n",s);stop_at=ticks;return true;}
static bool fake_info(void*c,risc_display_info_v1*s){CHECK_IO();(void)c;*s=(risc_display_info_v1){.api_version=1,.struct_size=sizeof(*s),.width=PANEL_W,.height=PANEL_H,.preferred_format=PIXEL_FORMAT,.nominal_refresh_millihz=60000,.typical_present_latency_us=16000,.supported_formats=RISC_DISPLAY_FORMAT_BIT(PIXEL_FORMAT),.flags=PIXEL_FORMAT==RISC_DISPLAY_FORMAT_MONO1?RISC_DISPLAY_INFO_RETAINS_IMAGE|RISC_DISPLAY_INFO_PARTIAL_DAMAGE:0};if(loss_case("panel-wide"))s->width=320;if(loss_case("panel-mono")){s->preferred_format=RISC_DISPLAY_FORMAT_MONO1;s->supported_formats=RISC_DISPLAY_FORMAT_BIT(RISC_DISPLAY_FORMAT_MONO1);}return true;}
static bool fake_frame(void*c,uint32_t f,risc_display_surface_v1*s){CHECK_IO();(void)c;assert(!frames);frames=1;*s=(risc_display_surface_v1){.frame=1,.pixels=pixels,.width=PANEL_W,.height=PANEL_H,.stride_bytes=STRIDE_BYTES,.size_bytes=sizeof(pixels),.pixel_format=f};return true;}
static void fake_frame_release(void*c,risc_display_frame_v1 f){CHECK_IO();(void)c;assert(frames&&f==1);frames=0;}
static bool fake_submit(void*c,risc_display_frame_v1 f,const risc_display_rect_v1*r,size_t n,const risc_display_present_options_v1*o,risc_display_present_token_v1*t){CHECK_IO();(void)c;(void)r;(void)n;assert(frames&&f==1);frames=0;
#ifdef POINTS_PAPER_RENDER
 assert(o->intent==RISC_DISPLAY_PRESENT_LOW_LATENCY);
#else
 (void)o;
#endif
 if(text_granted){
#ifdef POINTS_PAPER_RENDER
 /* The visible Q-key frame must occupy the same physical coordinates used
  * by the installed portrait app and raw portrait touch source. */
 /* Sample a straight border and its interior, away from rounded corners. */
 assert(physical_black(52,372));assert(!physical_black(39,390));
#endif
 host_frames++;if(getenv("POINTS_DELAY"))present_pending=30;
 }else app_frames++;*t=++presents;save_frame();return true;}
static bool fake_present(void*c,risc_display_present_token_v1 t,risc_display_present_status_v1*s){CHECK_IO();(void)c;assert(t);s->state=present_pending?RISC_DISPLAY_PRESENT_ACTIVE:RISC_DISPLAY_PRESENT_COMPLETE;if(present_pending)present_pending--;return true;}
static const risc_display_output_api_v1 display_api={.api_version=1,.struct_size=sizeof(display_api),.get_info=fake_info,.acquire=fake_frame,.release=fake_frame_release,.submit=fake_submit,.present_status=fake_present};
static uint64_t fake_sub(void*c){CHECK_IO();(void)c;assert(!subs);subs++;
 touch_head=touch_count=0;return 1;}
static bool fake_unsub(void*c,uint64_t n){CHECK_IO();(void)c;assert(n==1&&subs);
 if(text_granted&&host_frames&&getenv("POINTS_CASE")&&!strcmp(getenv("POINTS_CASE"),"retained"))return false;
 subs--;touch_head=touch_count=0;return true;}
static bool action_ready(const char *gate){
 if(!strcmp(gate,"text"))return text_granted&&host_frames>host_session_frames;
 assert(!strcmp(gate,"app"));return !text_granted&&app_frames&&app_frames>=app_resume_frame;
}
static bool fake_touch_poll(void*c,size_t n){CHECK_IO();
 (void)c;assert(n==1||n==2);polls++;
 if(action_cursor>=action_count||!action_ready(actions[action_cursor].gate))return true;
 if(action_gate_wait){next_action_at=ticks+actions[action_cursor].delay_ms;action_gate_wait=false;}
 if(ticks<next_action_at)return true;
 const char *kind=actions[action_cursor].kind;
 if(!strcmp(kind,"back")||!strcmp(kind,"home")){
  assert(!touch_down&&!navigation_pressed);
  navigation_pressed=!strcmp(kind,"back")?RISC_NAV_BACK:RISC_NAV_HOME;
 }else{
  unsigned event_kind;
  if(!strcmp(kind,"down")){assert(!touch_down);touch_down=true;event_kind=RISC_TOUCH_EVENT_DOWN;}
  else if(!strcmp(kind,"move")){assert(touch_down);event_kind=RISC_TOUCH_EVENT_MOVE;}
  else{assert(!strcmp(kind,"up")&&touch_down);touch_down=false;event_kind=RISC_TOUCH_EVENT_UP;}
  touch_x=actions[action_cursor].x;touch_y=actions[action_cursor].y;
  assert(touch_x>=0&&touch_x<TOUCH_W&&touch_y>=0&&touch_y<TOUCH_H);
  assert(subs==1&&touch_count<TOUCH_QUEUE_CAPACITY);
  touch_events[(touch_head+touch_count++)%TOUCH_QUEUE_CAPACITY]=(risc_touch_event_v1){
   .sequence=++touch_sequence,.timestamp_ms=ticks,.kind=event_kind,.id=1,
   .x=(uint16_t)touch_x,.y=(uint16_t)touch_y};touch_edges++;
  if(getenv("POINTS_CASE")&&!strcmp(getenv("POINTS_CASE"),"rapid-repeat")&&text_granted&&touch_x==47&&touch_y==97){
   assert(present_pending);if(!rapid_edges)rapid_frame=host_frames;assert(host_frames==rapid_frame);rapid_edges++;
  }
 }
 fprintf(stderr,"input at %u ms: %s %s %d %d\n",ticks,actions[action_cursor].gate,kind,actions[action_cursor].x,actions[action_cursor].y);
 const char *previous_gate=actions[action_cursor].gate;
 if(++action_cursor<action_count){
  action_gate_wait=strcmp(previous_gate,actions[action_cursor].gate)!=0;
  next_action_at=ticks+actions[action_cursor].delay_ms;
  if(getenv("POINTS_CASE")&&!strcmp(getenv("POINTS_CASE"),"rapid-repeat")&&text_granted&&actions[action_cursor].delay_ms<=10){
   ticks=next_action_at;return fake_touch_poll(c,n);
  }
 }
 return true;
}
static int32_t fake_next(void*c,uint64_t n,risc_touch_event_v1*e){CHECK_IO();(void)c;assert(n==1&&subs);
 if(!touch_count)return 0;
 *e=touch_events[touch_head];touch_head=(touch_head+1)%TOUCH_QUEUE_CAPACITY;touch_count--;return 1;}
static bool fake_snapshot(void*c,risc_touch_snapshot_v1*s){CHECK_IO();(void)c;
 *s=(risc_touch_snapshot_v1){.width=TOUCH_W,.height=TOUCH_H,.sequence=touch_sequence,.timestamp_ms=ticks};
 if(touch_down){s->contact_count=1;s->contacts[0]=(risc_touch_contact_v1){.id=1,.x=(uint16_t)touch_x,.y=(uint16_t)touch_y};}
 return true;}
static const risc_touch_api_v1 touch_api={1,sizeof(touch_api),NULL,fake_sub,fake_unsub,fake_touch_poll,fake_next,fake_snapshot};
static bool fake_battery(void*c,risc_battery_sample_v1*s){CHECK_IO();(void)c;*s=(risc_battery_sample_v1){.percent=73,.millivolts=3970,.flags=RISC_BATTERY_CHARGING};return true;}
static const risc_battery_gauge_api_v1 battery_api={1,sizeof(battery_api),NULL,fake_battery};
static bool fake_rtc(void*c,twatch_rtc_time_v1*s){CHECK_IO();(void)c;*s=(twatch_rtc_time_v1){2026,10,4,0,20,34,12};return true;}
static bool fake_write(void*c,const twatch_rtc_time_v1*s){CHECK_IO();(void)c;(void)s;assert(!"Unexpected RTC write in read-only audit");return false;}
static const twatch_rtc_api_v1 rtc_api={.api_version=2,.struct_size=sizeof(rtc_api),.read=fake_rtc,.write=fake_write};
static int32_t fake_get(void*c,const char*k,void*b,uint32_t cap,uint32_t*s){CHECK_IO();(void)c;*s=0;for(unsigned i=0;i<32;i++)if(!strcmp(k,cells[i].key)){*s=cells[i].size;if(cap<*s)return RISC_KEY_VALUE_BUFFER_SMALL;memcpy(b,cells[i].bytes,*s);
#ifdef POINTS_WATCH_RENDER
 if(text_grants&&!text_granted&&!strcmp(k,POINTS_META_KEY)&&loss_case("loss-kv-get"))runtime_lost=true;
#endif
 return 0;}return RISC_KEY_VALUE_NOT_FOUND;}
static int32_t fake_put(void*c,const char*k,const void*b,uint32_t n){CHECK_IO();assert(!text_granted);if(!strcmp(k,POINTS_META_KEY))name_writes++;if(!strcmp(k,POINTS_CONFIG_KEY))point_writes++;(void)c;assert(n<=64&&strlen(k)<16);unsigned i;for(i=0;i<32&&cells[i].key[0]&&strcmp(k,cells[i].key);i++);assert(i<32);strcpy(cells[i].key,k);memcpy(cells[i].bytes,b,n);cells[i].size=n;
#ifdef POINTS_WATCH_RENDER
 if(text_grants&&!text_granted&&!strcmp(k,POINTS_META_KEY)&&loss_case("loss-kv-put"))runtime_lost=true;
#endif
 return 0;}
static const risc_key_value_v1 kv_api={1,sizeof(kv_api),NULL,fake_get,fake_put};
static int32_t fake_alarm_status(void*c,alarm_status_v1*s){CHECK_IO();(void)c;*s=(alarm_status_v1){.api_version=1,.struct_size=sizeof(*s),.state=ALARM_STATE_READY,.mode=ALARM_MODE_BOTH};return ALARM_OK;}
static int32_t fake_alarm_step(void*c){CHECK_IO();(void)c;return ALARM_OK;}
static int32_t fake_alarm_ack(void*c,const alarm_token_v1*t){CHECK_IO();(void)c;(void)t;return ALARM_OK;}
static int32_t fake_alarm_prepare(void*c,alarm_sleep_v1*s){CHECK_IO();(void)c;*s=(alarm_sleep_v1){.struct_size=sizeof(*s)};return ALARM_OK;}
static const alarm_service_v1 alarm_api={1,sizeof(alarm_api),NULL,fake_alarm_status,fake_alarm_step,fake_alarm_step,fake_alarm_ack,fake_alarm_prepare,fake_alarm_step};
static bool fake_nav(void*c,risc_input_navigation_frame_v1*s){CHECK_IO();(void)c;*s=(risc_input_navigation_frame_v1){0};
#ifdef PORTABLE_NATIVE_CUSTODY_FENCE
 if(ticks>=stop_at&&!text_granted)s->pressed=RISC_NAV_BACK;
#endif
 s->pressed|=navigation_pressed;navigation_pressed=0;
 return true;}
static bool fake_foreground(void*c,const risc_input_foreground_v1*s,size_t n){CHECK_IO();(void)c;(void)s;(void)n;return true;}
static bool fake_reset(void*c){CHECK_IO();(void)c;navigation_pressed=0;return true;}
static const risc_input_navigation_api_v1 nav_api={1,sizeof(nav_api),NULL,fake_nav,fake_foreground,fake_reset};
const risc_input_navigation_api_v1 *portable_input_navigation_open(const risc_runtime_api_v1*r){(void)r;return &nav_api;}
void portable_input_navigation_close(const risc_runtime_api_v1*r){(void)r;}
int portable_app_alarm_sleep(const risc_runtime_api_v1*r,const risc_display_output_api_v1*d,const risc_battery_gauge_api_v1*b,const alarm_service_v1*a){(void)r;(void)d;(void)b;(void)a;assert(!"Unexpected hardware sleep in audit");return 0;}
static bool radio_enabled(void*c,bool on){CHECK_IO();(void)c;assert(!radio_owned);radio_control_calls++;radio_state=on?1:0;return true;}
static bool radio_status(void*c,uint8_t*out){CHECK_IO();(void)c;*out=(uint8_t)radio_state;return true;}
static const portable_bluetooth_control_v1 radio_api={1,sizeof(radio_api),NULL,NULL,NULL,radio_enabled,radio_status};
static wifi_link_t wifi_status(void*c){(void)c;return WIFI_LINK_DOWN;}
static bool wifi_disconnect(void*c){CHECK_IO();(void)c;return true;}
static const wifi_api_v1 wifi_api={.api_version=1,.struct_size=sizeof(wifi_api),.status=wifi_status,.disconnect_checked=wifi_disconnect};
#include "TelemetryBroadcastV1.h"
static unsigned broadcast_pauses,broadcast_steps;
static bool fake_broadcast_pause(void*c){CHECK_IO();(void)c;assert(!native_retained);broadcast_pauses++;return true;}
static bool fake_broadcast_step(void*c,bool allow,const telemetry_broadcast_policy_v1*p){CHECK_IO();(void)c;(void)p;(void)allow;assert(!native_retained);broadcast_steps++;return true;}
static bool fake_broadcast_status(void*c,telemetry_broadcast_status_v1*s){CHECK_IO();(void)c;assert(!native_retained);*s=(telemetry_broadcast_status_v1){.struct_size=sizeof(*s),.state=TELEMETRY_BROADCAST_OFF};return true;}
static int32_t fake_broadcast_enum(void*c,uint32_t i,risc_telemetry_field_v1*f){CHECK_IO();(void)c;(void)i;(void)f;assert(!native_retained);return 0;}
static int32_t fake_broadcast_read(void*c,uint32_t i,int32_t*v){CHECK_IO();(void)c;(void)i;(void)v;assert(!native_retained);return 0;}
static const telemetry_broadcast_v1 broadcast_api={1,sizeof(broadcast_api),NULL,fake_broadcast_step,fake_broadcast_pause,fake_broadcast_status,fake_broadcast_enum,fake_broadcast_read};
#include "ContextsServiceV1.h"
static unsigned context_steps,context_pauses,context_captures;
static bool context_step(void*c,const contexts_policy_v1*p){CHECK_IO();(void)c;assert(p&&p->struct_size==sizeof(*p));context_steps++;return true;}
static bool context_pause(void*c){CHECK_IO();(void)c;context_pauses++;return true;}
static bool context_status(void*c,contexts_status_v1*s){CHECK_IO();(void)c;*s=(contexts_status_v1){.struct_size=sizeof(*s),.state=CONTEXTS_OFF};return true;}
static bool context_mask(void*c,uint32_t a){CHECK_IO();(void)c;(void)a;return false;}
static bool context_export(void*c,uint32_t a,uint32_t b,uint32_t d,const void*e,uint32_t n){CHECK_IO();(void)c;(void)a;(void)b;(void)d;(void)e;(void)n;return false;}
static bool context_result(void*c,uint32_t a,uint32_t b){CHECK_IO();(void)c;(void)a;(void)b;return false;}
static bool context_preset(void*c,uint32_t a,uint32_t b,uint32_t d){CHECK_IO();(void)c;(void)a;(void)b;(void)d;return false;}
static int32_t context_label(void*c,uint32_t a,uint32_t b,contexts_label_v1*l){CHECK_IO();(void)c;(void)a;(void)b;(void)l;return 0;}
static bool context_claim(void*c,uint32_t a,uint32_t b,const char*n,uint32_t d){CHECK_IO();(void)c;(void)a;(void)b;(void)n;(void)d;return false;}
static bool context_capture(void*c){CHECK_IO();(void)c;context_captures++;return true;}
static const contexts_service_v1 context_api={.api_version=1,.struct_size=sizeof(context_api),.step=context_step,.pause=context_pause,.status=context_status,.request_export=context_mask,.begin_export=context_mask,.export_record=context_export,.finish_export=context_result,.label=context_label,.claim_preset=context_claim,.preset_result=context_preset,.capture_audio=context_capture};

#ifdef POINTS_WATCH_RENDER
static int32_t proxy_text_open(void*c,const risc_text_entry_request_v1*q,uint64_t*t){(void)c;CHECK_IO();const risc_text_entry_api_v1*p=text_driver->capability;assert(q->capacity==POINTS_CUSTOM_NAME_MAX+1&&!strcmp(q->label,"Custom type")&&!(q->reserved&RISC_TEXT_ENTRY_REQUEST_MASKED));assert(text_grants&&text_grants<=8);memcpy(requests[text_grants-1],q->text,POINTS_CUSTOM_NAME_MAX+1);int32_t rc=p->open(p->context,q,t);if(loss_case("loss-open"))runtime_lost=true;return rc;}
static int32_t proxy_text_poll(void*c,uint64_t t,risc_text_entry_state_v1*q){(void)c;CHECK_IO();const risc_text_entry_api_v1*p=text_driver->capability;int32_t rc=p->poll(p->context,t,q);if(loss_case("loss-poll"))runtime_lost=true;return rc;}
static int32_t proxy_text_close(void*c,uint64_t t){(void)c;CHECK_IO();const risc_text_entry_api_v1*p=text_driver->capability;int32_t rc=p->close(p->context,t);if(loss_case("loss-close"))runtime_lost=true;return rc;}
static const risc_text_entry_api_v1_home_reason text_proxy={{1,sizeof(text_proxy),NULL,proxy_text_open,proxy_text_poll,proxy_text_close},RISC_TEXT_ENTRY_HOME_REASON_TAG,RISC_TEXT_ENTRY_HOME_REASON_VERSION};
#endif
static bool fake_acquire(const char*n,uint32_t v,uint64_t id,risc_runtime_capability_v1*g){CHECK_IO();(void)id;assert(g->struct_size==sizeof(*g));
if(!strcmp(n,"contexts.service")){assert(v==1&&!id);g->api=&context_api;}
 else if(!strcmp(n,"telemetry.broadcast")){assert(v==1&&!id);g->api=&broadcast_api;}
 else if(!strcmp(n,"display.output")&&v==1)g->api=&display_api;else if(!strcmp(n,"input.touch.raw")&&v==1)g->api=&touch_api;else if(!strcmp(n,"board.battery")&&v==1)g->api=&battery_api;else if(!strcmp(n,"rtc.clock")&&v==2)g->api=&rtc_api;else if(!strcmp(n,"storage.key-value")&&v==1)g->api=&kv_api;else if(!strcmp(n,"bluetooth.hci")&&v==1)g->api=&radio_api;else if(!strcmp(n,"net.wifi")&&v==1)g->api=&wifi_api;else if(!strcmp(n,"alarm.service")&&v==
1
 )g->api=&alarm_api;else if(!strcmp(n,RISC_TEXT_ENTRY_CAPABILITY)&&v==1){
 if(getenv("POINTS_CASE")&&!strcmp(getenv("POINTS_CASE"),"unavailable"))return false;
 #ifdef POINTS_WATCH_RENDER
 if(loss_case("loss-acquire-fail")){runtime_lost=true;return false;}
#endif
 assert(!text_granted);text_granted=true;text_grants++;host_session_frames=host_frames;
#ifdef POINTS_WATCH_RENDER
 g->api=&text_proxy;
#else
 g->api=text_driver->capability;
#endif
 }else return false;g->slot=++grant_serial;assert(grant_serial<8192);grant_instances[grant_serial]=id;g->generation=1;grants++;
#ifdef POINTS_WATCH_RENDER
 if((is_text_api(g->api)&&loss_case("loss-acquire"))||(g->api==&kv_api&&text_grants&&!text_granted&&loss_case("loss-kv-acquire")))runtime_lost=true;
#endif
 return true;}
static bool fake_release(risc_runtime_capability_v1*g){CHECK_IO();assert(g->api&&grants);

bool released_text=is_text_api(g->api);bool released_kv=g->api==&kv_api&&grant_instances[g->slot]==5;
 if(released_text){assert(text_driver->quiesce()&&!frames);text_granted=false;app_resume_frame=app_frames+1;}
#ifndef POINTS_WATCH_RENDER
 (void)released_kv;
#endif
*g=(risc_runtime_capability_v1){.struct_size=sizeof(*g)};grants--;
#ifdef POINTS_WATCH_RENDER
 if((released_text&&loss_case("loss-release"))||(released_kv&&text_grants&&!text_granted&&loss_case("loss-kv-release")))runtime_lost=true;
#endif
 return true;}
static const risc_runtime_api_v1 runtime_api={

 .api_version=1,.struct_size=sizeof(runtime_api),.health=fake_health,.yield_ms=fake_yield,.diagnostic=fake_diag,.request_launch=fake_launch,.acquire=fake_acquire,.release=fake_release,
#ifdef RISC_RUNTIME_RETAIN_INVOCATION_V1_SIZE
 .retain_invocation=fake_retain_invocation,
#endif
};
const risc_runtime_api_v1 *risc_runtime_get_api(uint32_t v){
#ifdef RISC_RUNTIME_RETAIN_INVOCATION_V1_SIZE
 if(native_retained)return NULL;
#ifdef POINTS_WATCH_RENDER
 if(runtime_lost)return NULL;
#endif
#endif
 return v==1?&runtime_api:NULL;}
static uint64_t sensor_now(void*c){CHECK_IO();(void)c;return ticks;}
int main(int argc,char**argv){
 assert(argc>=2);directory=argv[1];memset(pixels,0xa5,sizeof(pixels));
 if(argc>2){FILE*f=fopen(argv[2],"r");assert(f);while(action_count<256&&fscanf(f,"%u %15s %15s %d %d",&actions[action_count].delay_ms,actions[action_count].gate,actions[action_count].kind,&actions[action_count].x,&actions[action_count].y)==5)action_count++;assert(feof(f));fclose(f);}
 if(action_count)next_action_at=actions[0].delay_ms;
 uint8_t policy[]={0x51,1,3,0xa6};assert(fake_put(NULL,"quick_radio",policy,4)==0);
 points_config cfg={.revision=3,.created=1000};
 for(unsigned i=0;i<POINTS_MAX;i++)cfg.points[i]=(points_item){.kind=POINTS_CUSTOM_1,.enabled=(uint8_t)(i&1),.mode=(uint8_t)(i%4),.weekdays=(uint8_t)(1u<<(i%7)),.hour=(uint8_t)(i*3),.minute=(uint8_t)(i*7),.duration_minutes=(uint16_t)(3+i*37),.notify_end=(uint8_t)(i&1),.warn3=(uint8_t)((i>>1)&1)};
 points_config_encode(&cfg,seed_points);assert(fake_put(NULL,POINTS_CONFIG_KEY,seed_points,sizeof(seed_points))==0);
 points_meta meta={.revision=2,.custom={{.color=6,.name="Focus"},{.color=2,.name="Other"}}};
 points_meta_encode(&meta,seed_meta);assert(fake_put(NULL,POINTS_META_KEY,seed_meta,sizeof(seed_meta))==0);
 name_writes=point_writes=0;
 risc_platform_clock_api_v1 clock={1,sizeof(clock),NULL,sensor_now,NULL};
scene_driver=points_scene_driver_get(2);text_driver=points_text_driver_get(2);assert(scene_driver&&text_driver);
const risc_driver_v2 *profile_driver=points_profile_driver_get(2);assert(profile_driver&&profile_driver->start(NULL,0));
const risc_scene_profile_v1 *profile=profile_driver->capability;
risc_provider_dependency_v1 scene_deps[]={{"display.output",1,&display_api},{"input.touch.raw",1,&touch_api},{"platform.clock",1,&clock},{"ui.presentation-profile",1,profile}};
assert(scene_driver->start(scene_deps,4));risc_provider_dependency_v1 text_deps[]={{RISC_SCENE_CAPABILITY,1,scene_driver->capability}};assert(text_driver->start(text_deps,1));
int init=app_module_init();if(loss_case("panel-wide")||loss_case("panel-mono")){assert(init!=0);app_module_fini();assert(!grants&&!subs&&!frames);puts("Watch-only profile rejects incompatible display before presentation");return 0;}assert(init==0);app_main();
app_module_fini();
#ifdef POINTS_WATCH_RENDER
if(runtime_lost){assert(native_retained&&portable_text_adapter_retained()&&(loss_case("loss-kv-release")?launches<=1:!launches));assert(grants==retained_grants&&subs==retained_subs&&frames==retained_frames);assert(app_module_init()!=0);puts("Runtime loss: silent retention, frozen resources, no further provider/runtime I/O, and re-entry refused");return 0;}
#endif
if(getenv("POINTS_CASE")&&!strcmp(getenv("POINTS_CASE"),"retained")){
 assert(portable_text_adapter_retained()&&text_granted&&grants&&subs&&!frames&&!name_writes&&!launches);
 assert(!scene_driver->quiesce()&&!text_driver->quiesce());
 assert(app_module_init()!=0);
#ifdef RISC_RUNTIME_RETAIN_INVOCATION_V1_SIZE
 assert(native_retained&&grants==retained_grants&&subs==retained_subs&&frames==retained_frames);
#endif
 puts("Actual Points app_main retained failed shared-host cleanup; fini did not free grants/subscriptions; re-entry refused");return 0;
}
assert(!grants&&!frames&&!subs&&!radio_owned);
assert(action_cursor==action_count&&!touch_down&&!navigation_pressed);
assert(broadcast_pauses&&broadcast_steps&&context_steps&&context_pauses);
 if(getenv("POINTS_HOME"))assert(!launches&&ticks<stop_at);
if(getenv("POINTS_BACK"))assert(launches==1&&action_cursor==action_count);
const char*mode=getenv("POINTS_CASE");assert(mode);
uint8_t current[POINTS_RECORD_SIZE];uint32_t size=0;
assert(fake_get(NULL,POINTS_CONFIG_KEY,current,sizeof(current),&size)==0&&size==sizeof(current));
if(!strcmp(mode,"schedule-save")||!strcmp(mode,"delete-point")){
 points_config changed;assert(points_config_decode(&changed,current,size)&&point_writes==1);
 for(unsigned i=1;i<POINTS_MAX;i++)assert(!memcmp(&changed.points[i],&cfg.points[i],sizeof(points_item)));
 if(!strcmp(mode,"delete-point")){points_item empty={0};assert(!memcmp(&changed.points[0],&empty,sizeof(empty)));}
 else {points_item wanted={.kind=POINTS_CUSTOM_1,.enabled=1,.mode=2,.weekdays=127,.hour=1,.minute=1,.duration_minutes=64,.notify_end=1,.warn3=1};assert(!memcmp(&changed.points[0],&wanted,sizeof(wanted)));}
}else assert(!point_writes&&!memcmp(current,seed_points,sizeof(current)));
assert(fake_get(NULL,POINTS_META_KEY,current,sizeof(current),&size)==0&&size==sizeof(current));
points_meta saved;assert(points_meta_decode(&saved,current,size));
if(!strcmp(mode,"save")||!strcmp(mode,"save-delayed")){assert(name_writes==1&&text_grants==1&&!strcmp(saved.custom[0].name,"FocusW"));}
else if(!strcmp(mode,"rapid-repeat")){fprintf(stderr,"rapid edges=%u writes=%u grants=%u name=%s\n",rapid_edges,name_writes,text_grants,saved.custom[0].name);assert(rapid_edges==4&&name_writes==1&&text_grants==1&&!strcmp(saved.custom[0].name,"FocusWW"));}
else if(!strcmp(mode,"repeat")){assert(text_grants==3&&name_writes==1&&!strcmp(requests[0],"Focus")&&!strcmp(requests[1],"FocusW")&&!strcmp(requests[2],"FocusW")&&!strcmp(saved.custom[0].name,"FocusWW"));}
else if(!strcmp(mode,"color-save")){assert(name_writes==1&&text_grants==1&&!strcmp(saved.custom[0].name,"FocusW")&&saved.custom[0].color==4);}
else if(!strcmp(mode,"limit")){assert(name_writes==1&&!strcmp(saved.custom[0].name,"FocusWWWWWWWW"));}
else if(!strcmp(mode,"delete")){assert(name_writes==1&&!strcmp(saved.custom[0].name,"Focu"));}
else {assert(!name_writes&&!memcmp(current,seed_meta,sizeof(current)));}
assert(!memcmp(&saved.custom[1],&meta.custom[1],sizeof(meta.custom[1])));
if(strcmp(mode,"color-save"))assert(saved.custom[0].color==meta.custom[0].color);
assert(app_frames>0);if(text_grants)assert(host_frames>0);assert(presents>0);assert(text_driver->quiesce());text_driver->stop();assert(scene_driver->quiesce());scene_driver->stop();assert(profile_driver->quiesce());profile_driver->stop();
printf("Production app/adapter capture: %u frames, %u polls, %u ms; all grants released; stride guards intact; %u/%u input actions, %u ordered touch edges\n",presents,polls,ticks,action_cursor,action_count,touch_edges);return 0;}
