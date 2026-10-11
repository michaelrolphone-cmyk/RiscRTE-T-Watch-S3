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
#include "AlarmServiceV1.h"
#include "PortableBluetoothHost.h"
#include "RiscBluetoothHidV1.h"
#include "WifiApi.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef HID_RENDER_RUNTIME_DIAGNOSTICS
void hid_serial_start(void);void hid_serial_line(const char*);void hid_serial_finish(void);
#endif
void app_main(void);int app_module_init(void);void app_module_fini(void);
static unsigned ticks,polls,grants,frames,subs,presents;
#ifdef HID_RENDER_RESIDENT
#include "RiscResidentShellV1.h"
#include "RiscRealtimeV1.h"
#include "AlarmServiceV2.h"
typedef struct {alarm_service_v1 service;uint32_t output_modes;} alarm_service_outputs_v1;
static unsigned resident_polls,resident_policies,policy_at;
static bool resident_jump;
#endif
static unsigned stop_poll=240;
static bool hid_owned,allow_pair,paired_confirm,paired_reject;
static unsigned diagnostic_lines, pairing_contacts, pairing_requests, pairing_results, pairing_confirmations;
static bool diagnostic_moved,diagnostic_multitouch,diagnostic_gap,diagnostic_transport,diagnostic_closed,transport_failed;
static unsigned hid_opens,hid_closes,hid_polls,hid_keyboard_reports,hid_mouse_reports,hid_releases;
static unsigned hid_scroll_reports,drag_moves,drag_releases;
static int scroll_x,scroll_y;
static bool drag_held;
static uint8_t held_mod,held_key,held_mouse;
static uint64_t touch_sequence;
static unsigned touch_count;
static bool gap_given,alarm_dismissed,sleep_jumped,sleep_seen,low_battery_jumped,low_battery_seen;
#ifdef HID_RENDER_WATCH_TOUCH
static const risc_touch_api_v1 *watch_touch;
static uint64_t watch_subscriptions[5];
const risc_touch_api_v1 *hid_watch_touch_start(void);
void hid_watch_touch_stop(void);
#else
static risc_touch_snapshot_v1 prior_touch;
#endif
static struct {bool live;uint64_t sequence;} subscribers[5];
static unsigned radio_sends,radio_claims,radio_closes,radio_state,launches,reports,radio_control_calls;static bool radio_owned;
static uint8_t command_ack[6];static bool ack_ready,advertising;
static uint16_t pixels[800*484];
#ifdef HID_RENDER_PAPER
static const bool paper_profile=true;
#else
static const bool paper_profile=false;
#endif
static unsigned close_attempts,unsub_attempts,release_attempts,save_attempts;
static const char *directory;
static struct {unsigned at;int x,y;} actions[256];static unsigned action_count;
static struct {char key[16];unsigned char bytes[64];uint32_t size;} cells[32];
static void save_frame(void) {
 if(!directory)return;
 char path[1024];snprintf(path,sizeof(path),"%s/frame-%03u.%s",directory,presents,paper_profile?"pbm":"ppm");
 FILE*f=fopen(path,"wb");assert(f);
 if(paper_profile){fprintf(f,"P4\n480 800\n");unsigned char *p=(unsigned char*)pixels;
  for(unsigned y=0;y<800;y++)for(unsigned b=0;b<60;b++){unsigned char bits=0;for(unsigned bit=0;bit<8;bit++){unsigned x=b*8+bit;/* physical=(logical y,479-logical x) */if(p[(479-x)*104+y/8]&(0x80u>>(y%8)))bits|=0x80u>>bit;}fputc(bits,f);}
  for(unsigned y=0;y<480;y++)for(unsigned x=100;x<104;x++)assert(p[y*104+x]==0xa5);
 } else {fprintf(f,"P6\n240 240\n255\n");for(unsigned y=0;y<240;y++){for(unsigned x=0;x<240;x++){uint16_t v=pixels[y*244+x];unsigned char rgb[]={(v>>11)*255/31,((v>>5)&63)*255/63,(v&31)*255/31};assert(fwrite(rgb,1,3,f)==3);}for(unsigned x=240;x<244;x++)assert(pixels[y*244+x]==0xa5a5);}}
 assert(!fclose(f));
}
static bool fake_health(risc_runtime_health_v1*h){h->uptime_ms=ticks;
#ifdef HID_RENDER_RESIDENT
 return true;
#else
 return polls<stop_poll;
#endif
}
static void fake_yield(uint32_t n){ticks+=n;
#ifdef HID_RENDER_RESIDENT
 if(polls>=20&&!resident_jump){ticks+=61000;resident_jump=true;}
#endif
if(getenv("HID_RENDER_LOW_BATTERY")&&polls>=40&&!low_battery_jumped){low_battery_jumped=true;ticks+=5000;}if(getenv("HID_RENDER_SLEEP")&&polls>=40&&!sleep_jumped){sleep_jumped=true;ticks+=60001;}}
static bool fake_diag(const char*s){
 assert(s&&!strstr(s,"000042")&&!strstr(s,"pairing_number"));
 assert(++diagnostic_lines<80);
 low_battery_seen|=strstr(s,"LOW_BATTERY crossing=applied-once")!=NULL;
 diagnostic_transport|=strstr(s,"HID stop reason=Bluetooth error")!=NULL;
 diagnostic_closed|=strstr(s,"HID closed status=1 state=0 flags=16 error=12")!=NULL;
 if(strstr(s,"HID pairing contact"))pairing_contacts++;
 if(strstr(s,"HID pairing response")&&strstr(s," requested"))pairing_requests++;
 if(strstr(s,"HID pairing response")&&strstr(s," result=ok"))pairing_results++;
 diagnostic_moved|=strstr(s,"reason=moved")!=NULL;
 diagnostic_multitouch|=strstr(s,"reason=multiple-contacts")!=NULL;
 diagnostic_gap|=strstr(s,"reason=event-gap")!=NULL;
#ifdef HID_RENDER_RUNTIME_DIAGNOSTICS
 hid_serial_line(s);
#endif
 fprintf(stderr,"%s\n",s);return true;
}
static bool fake_launch(const char*s){assert(!radio_owned&&!hid_owned);assert(!strcmp(s,getenv("HID_RENDER_HOME")?"default.elf":"springboard.elf"));launches++;printf("launch=%s\n",s);stop_poll=polls;return true;}
static bool fake_info(void*c,risc_display_info_v1*s){(void)c;*s=(risc_display_info_v1){.width=paper_profile?800:240,.height=paper_profile?480:240,.nominal_refresh_millihz=paper_profile?1000:60000,.typical_present_latency_us=paper_profile?200000:16000,.flags=RISC_DISPLAY_INFO_PARTIAL_DAMAGE|(paper_profile?RISC_DISPLAY_INFO_RETAINS_IMAGE:0),.supported_formats=RISC_DISPLAY_FORMAT_BIT(paper_profile?RISC_DISPLAY_FORMAT_MONO1:RISC_DISPLAY_FORMAT_RGB565)};return true;}
static bool fake_frame(void*c,uint32_t f,risc_display_surface_v1*s){(void)c;assert(!frames);frames=1;*s=(risc_display_surface_v1){.frame=1,.pixels=pixels,.width=paper_profile?800:240,.height=paper_profile?480:240,.stride_bytes=paper_profile?104:488,.size_bytes=sizeof(pixels),.pixel_format=f};return true;}
static void fake_frame_release(void*c,risc_display_frame_v1 f){(void)c;assert(frames&&f==1);frames=0;}
static bool fake_submit(void*c,risc_display_frame_v1 f,const risc_display_rect_v1*r,size_t n,const risc_display_present_options_v1*o,risc_display_present_token_v1*t){(void)c;(void)r;(void)n;(void)o;assert(frames&&f==1);frames=0;*t=++presents;save_frame();if(paper_profile)ticks+=1600;return true;}
static bool fake_present(void*c,risc_display_present_token_v1 t,risc_display_present_status_v1*s){(void)c;assert(t);s->state=RISC_DISPLAY_PRESENT_COMPLETE;return true;}
static bool fake_brightness(void*c,uint16_t level,uint16_t maximum){(void)c;assert(level<=maximum&&maximum==100);if(getenv("HID_RENDER_LOW_BATTERY"))assert(level==15&&!hid_owned);return true;}
static const risc_display_output_api_v1 display_api={.api_version=1,.struct_size=sizeof(display_api),.get_info=fake_info,.acquire=fake_frame,.release=fake_frame_release,.submit=fake_submit,.present_status=fake_present,.set_brightness=fake_brightness};
static void current_touch(risc_touch_snapshot_v1*s){
 *s=(risc_touch_snapshot_v1){.width=paper_profile?480:240,.height=paper_profile?800:240,.sequence=touch_sequence};
 if(getenv("HID_RENDER_RAW_HOME")&&polls==100)s->buttons=RISC_TOUCH_BUTTON_PRIMARY;
 for(unsigned i=0;i<action_count;i++)if(actions[i].at==polls){unsigned at=s->contact_count++;assert(at<5);s->contacts[at]=(risc_touch_contact_v1){.id=(uint8_t)(at+1),.x=(uint16_t)actions[i].x,.y=(uint16_t)actions[i].y};}
}
#ifdef HID_RENDER_WATCH_TOUCH
void hid_renderer_watch_report(risc_touch_snapshot_v1*s){current_touch(s);}
uint64_t hid_renderer_watch_millis(void){return ticks;}
#endif
static uint64_t fake_sub(void*c){(void)c;for(unsigned i=1;i<5;i++)if(!subscribers[i].live){subscribers[i].live=true;subscribers[i].sequence=touch_sequence;
#ifdef HID_RENDER_WATCH_TOUCH
watch_subscriptions[i]=watch_touch->subscribe(watch_touch->context);assert(watch_subscriptions[i]);
#endif
subs++;return i;}assert(!"too many subscribers");return 0;}
static bool fake_unsub(void*c,uint64_t n){(void)c;assert(n>0&&n<5&&subscribers[n].live&&subs);
/* A rejected unsubscribe preserves the real provider token for retry. */
if(getenv("HID_RENDER_CLEANUP")&&++unsub_attempts==1)return false;
#ifdef HID_RENDER_WATCH_TOUCH
assert(watch_touch->unsubscribe(watch_touch->context,watch_subscriptions[n]));watch_subscriptions[n]=0;
#endif

subscribers[n].live=false;subs--;return true;}
static bool fake_touch_poll(void*c,size_t n){(void)c;assert(n==1);
 /* The adapter owns time advancement; the app's second poll sees the same report. */
 if(!hid_owned||(++touch_count%2)==1){polls++;
#ifndef HID_RENDER_WATCH_TOUCH
risc_touch_snapshot_v1 next;current_touch(&next);next.sequence=prior_touch.sequence=0;if(memcmp(&next,&prior_touch,sizeof(next))){touch_sequence++;prior_touch=next;}
#endif
 }
#ifdef HID_RENDER_WATCH_TOUCH
 return watch_touch->poll(watch_touch->context,n);
#else
 return true;
#endif
}
static int32_t fake_next(void*c,uint64_t n,risc_touch_event_v1*e){(void)c;assert(n>0&&n<5&&subscribers[n].live);
 if(getenv("HID_RENDER_GAP")&&n==2&&polls>=40&&!gap_given){gap_given=true;subscribers[n].sequence=touch_sequence;
#ifdef HID_RENDER_WATCH_TOUCH
 while(watch_touch->next(watch_touch->context,watch_subscriptions[n],e)>0){}
#endif
 return -1;}
#ifdef HID_RENDER_WATCH_TOUCH
 return watch_touch->next(watch_touch->context,watch_subscriptions[n],e);
#else
 if(subscribers[n].sequence==touch_sequence)return 0;
 *e=(risc_touch_event_v1){.sequence=++subscribers[n].sequence};return 1;
#endif
}
static bool fake_snapshot(void*c,risc_touch_snapshot_v1*s){(void)c;
#ifdef HID_RENDER_WATCH_TOUCH
 return watch_touch->snapshot(watch_touch->context,s);
#else
 current_touch(s);return true;
#endif
}
static const risc_touch_api_v1 touch_api={1,sizeof(touch_api),NULL,fake_sub,fake_unsub,fake_touch_poll,fake_next,fake_snapshot};
static bool fake_battery(void*c,risc_battery_sample_v1*s){(void)c;*s=(risc_battery_sample_v1){.percent=(uint8_t)((getenv("HID_RENDER_LOW_BATTERY")&&polls>=40)?9:73),.millivolts=3970,.flags=RISC_BATTERY_CHARGING};return true;}
static const risc_battery_gauge_api_v1 battery_api={1,sizeof(battery_api),NULL,fake_battery};
static bool fake_rtc(void*c,twatch_rtc_time_v1*s){(void)c;*s=(twatch_rtc_time_v1){2026,10,4,0,20,34,12};return true;}
static bool fake_write(void*c,const twatch_rtc_time_v1*s){(void)c;(void)s;assert(!"Unexpected RTC write in read-only audit");return false;}
static const twatch_rtc_api_v1 rtc_api={.api_version=2,.struct_size=sizeof(rtc_api),.read=fake_rtc,.write=fake_write};
static int32_t fake_get(void*c,const char*k,void*b,uint32_t cap,uint32_t*s){(void)c;*s=0;for(unsigned i=0;i<32;i++)if(!strcmp(k,cells[i].key)){*s=cells[i].size;if(cap<*s)return RISC_KEY_VALUE_BUFFER_SMALL;memcpy(b,cells[i].bytes,*s);return 0;}return RISC_KEY_VALUE_NOT_FOUND;}
static int32_t fake_put(void*c,const char*k,const void*b,uint32_t n){(void)c;if(!strcmp(k,"hid_buttons")){save_attempts++;if(getenv("HID_RENDER_SAVE_FAIL")&&save_attempts==1)return RISC_KEY_VALUE_IO;}assert(n<=64&&strlen(k)<16);unsigned i;for(i=0;i<32&&cells[i].key[0]&&strcmp(k,cells[i].key);i++){}assert(i<32);strcpy(cells[i].key,k);memcpy(cells[i].bytes,b,n);cells[i].size=n;return 0;}
static const risc_key_value_v1 kv_api={1,sizeof(kv_api),NULL,fake_get,fake_put};
static int32_t fake_alarm_status(void*c,alarm_status_v1*s){(void)c;*s=(alarm_status_v1){.api_version=1,.struct_size=sizeof(*s),.state=ALARM_STATE_READY,.mode=ALARM_MODE_BOTH};
 if(getenv("HID_RENDER_ALARM")&&polls>=40&&!alarm_dismissed){s->state=ALARM_STATE_ALERT;s->occurrence=(alarm_token_v1){.kind=ALARM_KIND_COUNTDOWN,.revision=1,.deadline=1,.generation=1};}
 return ALARM_OK;}
static int32_t fake_alarm_step(void*c){(void)c;return ALARM_OK;}
static int32_t fake_alarm_ack(void*c,const alarm_token_v1*t){(void)c;assert(t->generation==1&&!hid_owned&&!held_mod&&!held_key&&!held_mouse);alarm_dismissed=true;return ALARM_OK;}
static int32_t fake_alarm_prepare(void*c,alarm_sleep_v1*s){(void)c;*s=(alarm_sleep_v1){.struct_size=sizeof(*s)};return ALARM_OK;}
static const alarm_service_outputs_v1 alarm_api={.service={1,sizeof(alarm_api),NULL,fake_alarm_status,fake_alarm_step,fake_alarm_step,fake_alarm_ack,fake_alarm_prepare,fake_alarm_step},
#ifdef HID_RENDER_PAPER
.output_modes=ALARM_MODE_VISUAL
#else
.output_modes=ALARM_MODE_BOTH
#endif
};
static bool fake_nav(void*c,risc_input_navigation_frame_v1*s){(void)c;*s=(risc_input_navigation_frame_v1){0};if(getenv("HID_RENDER_HOME")&&!getenv("HID_RENDER_RAW_HOME")&&polls==100){s->buttons=RISC_NAV_HOME;s->pressed=RISC_NAV_HOME;}return true;}
static bool fake_foreground(void*c,const risc_input_foreground_v1*s,size_t n){(void)c;(void)s;(void)n;return true;}
static bool fake_reset(void*c){(void)c;return true;}
static const risc_input_navigation_api_v1 nav_api={1,sizeof(nav_api),NULL,fake_nav,fake_foreground,fake_reset};
const risc_input_navigation_api_v1 *portable_input_navigation_open(const risc_runtime_api_v1*r){(void)r;return &nav_api;}
void portable_input_navigation_close(const risc_runtime_api_v1*r){(void)r;}
int portable_app_alarm_sleep(const risc_runtime_api_v1*r,const risc_display_output_api_v1*d,const risc_battery_gauge_api_v1*b,const alarm_service_v1*a){(void)r;(void)d;(void)b;(void)a;assert(getenv("HID_RENDER_SLEEP")&&!hid_owned&&!subs&&!frames);sleep_seen=true;return 0;}
static bool radio_enabled(void*c,bool on){(void)c;assert(!radio_owned);radio_control_calls++;radio_state=on?1:0;return true;}
static bool radio_status(void*c,uint8_t*out){(void)c;*out=(uint8_t)radio_state;return true;}
static bool radio_claim(void*c,uint64_t*out){(void)c;assert(!radio_owned);radio_owned=true;radio_state=1;radio_claims++;*out=1;reports=0;advertising=false;return true;}
static bool radio_send(void*c,uint64_t token,uint8_t type,const uint8_t*p,size_t n){(void)c;assert(radio_owned&&token==1&&type==1&&n==3u+p[2]);radio_sends++;uint8_t ack[]={0x0e,4,1,p[0],p[1],0};memcpy(command_ack,ack,6);ack_ready=true;if(p[0]==0x0c&&p[1]==0x20)advertising=true;return true;}
static int32_t radio_next(void*c,uint64_t token,uint8_t*type,uint8_t*p,size_t cap,size_t*n){
 (void)c;assert(radio_owned&&token==1&&cap>=1028);*type=4;
 if(ack_ready){memcpy(p,command_ack,6);*n=6;ack_ready=false;return 1;}
 if(advertising&&reports<6){uint8_t event[]={0x3e,30,2,1,0,1,1,2,3,4,5,6,18,4,9,'T','e','m',12,0x16,0xd2,0xfc,0x40,1,88,2,0xca,8,3,0x88,0x13,(uint8_t)-56};event[6]=(uint8_t)++reports;event[16]=(uint8_t)('0'+reports);memcpy(p,event,sizeof(event));*n=sizeof(event);return 1;}
 *n=0;return 0;
}
static int32_t radio_close(void*c,uint64_t token){(void)c;assert(radio_owned&&token==1);radio_owned=false;radio_closes++;advertising=ack_ready=false;return 1;}
static const portable_bluetooth_host_v1 radio_api={{1,sizeof(radio_api),NULL,NULL,NULL,radio_enabled,radio_status},radio_claim,radio_send,radio_next,radio_close};
static wifi_link_t wifi_status(void*c){(void)c;return WIFI_LINK_DOWN;}
static bool wifi_disconnect(void*c){(void)c;return true;}
static const wifi_api_v1 wifi_api={.api_version=1,.struct_size=sizeof(wifi_api),.status=wifi_status,.disconnect_checked=wifi_disconnect};
static bool fake_hid_open(void*c,const char*name,bool allow,uint64_t*t){(void)c;assert(name&&!hid_owned&&!radio_owned);hid_owned=true;allow_pair=allow;*t=77;hid_opens++;touch_count=0;return true;}
static bool fake_hid_poll(void*c,uint64_t t,uint32_t n){(void)c;assert(hid_owned&&t==77&&n==8);hid_polls++;if(getenv("HID_RENDER_PAIR_ERROR")&&polls>=60&&hid_opens==1){transport_failed=true;return false;}if(getenv("HID_RENDER_TRANSPORT_RECONNECT")&&polls>=40&&hid_opens==1){transport_failed=true;return false;}return true;}
static bool fake_hid_status(void*c,uint64_t t,risc_bluetooth_hid_status_v1*s){(void)c;assert(t==(hid_owned?77u:0u));
 *s=(risc_bluetooth_hid_status_v1){.struct_size=sizeof(*s),.state=hid_owned?RISC_HID_READY:RISC_HID_OFF,.flags=31,.connection_generation=1};
 if(hid_owned&&(getenv("HID_RENDER_PAIR")||getenv("HID_RENDER_PENDING_CANCEL"))&&!paired_confirm){s->state=RISC_HID_PAIR_CONFIRM;s->pairing_number=42;}
 if(hid_owned&&(getenv("HID_RENDER_PAIR_TIMEOUT")||getenv("HID_RENDER_PAIR_ERROR"))&&hid_opens==1){s->state=polls<60?RISC_HID_PAIR_CONFIRM:RISC_HID_ADVERTISING;s->pairing_number=polls<60?42:0;}
 if(transport_failed&&hid_opens==1){s->state=hid_owned?RISC_HID_FAULT:RISC_HID_OFF;s->flags=16;s->error=12;}
 if(hid_owned&&getenv("HID_RENDER_MOUSE_RECONNECT")&&polls>=40){
  if(polls<60){s->state=RISC_HID_ADVERTISING;s->flags=16;held_mod=held_key=held_mouse=0;}
  else {s->connection_generation=2;if(polls<70)s->flags&=~RISC_HID_MOUSE_READY;}
 }
 if(hid_owned&&getenv("HID_RENDER_DISCONNECT")&&polls>=40){s->state=RISC_HID_ADVERTISING;s->flags=16;}
 return true;
}
static bool fake_hid_confirm(void*c,uint64_t t,bool accept){(void)c;assert(t==77&&hid_owned);pairing_confirmations++;if(getenv("HID_RENDER_PAIR_RECOVERED"))assert(polls>=60);paired_confirm=accept;paired_reject=!accept;return true;}
static bool fake_hid_keyboard(void*c,uint64_t t,uint8_t mods,const uint8_t keys[6]){(void)c;assert(hid_owned&&t==77);held_mod=mods;held_key=keys[0];hid_keyboard_reports++;return true;}
static void observe_pointer(uint8_t b,int x,int y){
 if(getenv("HID_RENDER_SCROLL_X")||getenv("HID_RENDER_SCROLL_Y")||getenv("HID_RENDER_SCROLL_FREE"))assert(!b&&!x&&!y);
 if(b==1&&(x||y)){drag_moves++;drag_held=true;}
 if(!b&&drag_held){drag_releases++;drag_held=false;}
}
static bool fake_hid_mouse(void*c,uint64_t t,uint8_t b,int8_t x,int8_t y,int8_t w){(void)c;(void)x;(void)y;(void)w;assert(hid_owned&&t==77);
 if(getenv("HID_RENDER_MOUSE_RECONNECT"))assert(polls<40||polls>=70);
 if(getenv("HID_RENDER_TRANSPORT_RECONNECT")&&polls>=40)assert(hid_opens==2);
 observe_pointer(b,x,y);held_mouse=b;hid_mouse_reports++;return true;}
static bool fake_hid_scroll(void*c,uint64_t t,uint8_t b,int16_t x,int16_t y,int16_t wx,int16_t wy){
 assert(x>=-127&&x<=127&&y>=-127&&y<=127&&wx>=-127&&wx<=127&&wy>=-127&&wy<=127);
 if(getenv("HID_RENDER_SCROLL_X"))assert(!wy);
 if(getenv("HID_RENDER_SCROLL_Y"))assert(!wx);
 if(wx||wy){hid_scroll_reports++;scroll_x+=wx;scroll_y+=wy;}
 return fake_hid_mouse(c,t,b,(int8_t)x,(int8_t)y,0);
}
static bool fake_hid_release(void*c,uint64_t t){(void)c;assert(hid_owned&&t==77);held_mod=held_key=held_mouse=0;hid_releases++;return true;}
static bool fake_hid_close(void*c,uint64_t t){(void)c;assert(hid_owned&&t==77);if(getenv("HID_RENDER_REQUIRE_CONFIRM"))assert(paired_confirm||paired_reject);if(getenv("HID_RENDER_CLEANUP")&&++close_attempts==1)return false;held_mod=held_key=held_mouse=0;hid_owned=false;hid_closes++;return true;}
static bool fake_hid_forget(void*c){(void)c;assert(!hid_owned);return true;}
static bool fake_hid_battery(void*c,uint64_t t,uint8_t p){(void)c;assert(hid_owned&&t==77&&p==73);return true;}
static const risc_bluetooth_hid_scroll_api_v1 hid_api={
 .base={.base={1,sizeof(hid_api),NULL,fake_hid_open,fake_hid_poll,fake_hid_status,fake_hid_confirm,fake_hid_keyboard,fake_hid_mouse,fake_hid_release,fake_hid_close,fake_hid_forget,fake_hid_battery}},
 .mouse_scroll=fake_hid_scroll
};
static bool fake_acquire(const char*n,uint32_t v,uint64_t id,risc_runtime_capability_v1*g){(void)id;assert(g->struct_size==sizeof(*g));if(!strcmp(n,"display.output")&&v==1)g->api=&display_api;else if(!strcmp(n,"input.touch.raw")&&v==1){assert(id==0||id==(paper_profile?4:6));g->api=&touch_api;}else if(!strcmp(n,"board.battery")&&v==1)g->api=&battery_api;else if(!strcmp(n,"rtc.clock")&&v==2)g->api=&rtc_api;else if(!strcmp(n,"storage.key-value")&&v==1)g->api=&kv_api;else if(!strcmp(n,"bluetooth.hci")&&v==1)g->api=&radio_api;else if(!strcmp(n,"bluetooth.hid")&&v==1){assert(id==0);g->api=&hid_api;}else if(!strcmp(n,"net.wifi")&&v==1)g->api=&wifi_api;else if(!strcmp(n,"alarm.service")&&v==1)g->api=&alarm_api;else return false;grants++;return true;}
static bool fake_release(risc_runtime_capability_v1*g){assert(g->api&&grants);if(g->api==&hid_api&&getenv("HID_RENDER_CLEANUP")&&++release_attempts==1)return false;*g=(risc_runtime_capability_v1){.struct_size=sizeof(*g)};grants--;return true;}
#ifdef HID_RENDER_RESIDENT
static int32_t resident_checkpoint_fixture(uint64_t invocation,const risc_resident_request_v1 *q,risc_resident_reply_v1 *r){
 assert(invocation==2 && q->struct_size==sizeof(*q) && r->struct_size==sizeof(*r));
 if(q->reason==RISC_RESIDENT_CHECKPOINT_POLL){resident_polls++;if((uint32_t)(ticks-policy_at)>=5000)r->flags=RISC_RESIDENT_REPLY_POLICY_REQUEST;}
 if(q->reason==RISC_RESIDENT_CHECKPOINT_POLICY){assert(!hid_owned);resident_policies++;policy_at=ticks;}
 return RISC_RESIDENT_OK;
}
static bool resident_get(risc_resident_client_v1 *out){*out=(risc_resident_client_v1){.api_version=1,.struct_size=sizeof(*out),.invocation=2,.role=RISC_RESIDENT_ROLE_FOREGROUND,.checkpoint=resident_checkpoint_fixture};return true;}
static int32_t resident_time(void*c,risc_realtime_snapshot_v1 *s){(void)c;*s=(risc_realtime_snapshot_v1){.struct_size=sizeof(*s),.validity=RISC_REALTIME_VALID,.epoch_seconds=1791584000+ticks/1000,.monotonic_before_us=(uint64_t)ticks*1000,.monotonic_after_us=(uint64_t)ticks*1000};return RISC_REALTIME_OK;}
static const risc_realtime_api_v1 resident_clock={1,sizeof(resident_clock),&ticks,resident_time};
static const alarm_service_descriptor_v2 resident_alarm={.base={2,sizeof(resident_alarm),NULL,fake_alarm_status,fake_alarm_step,fake_alarm_step,fake_alarm_ack,fake_alarm_prepare,fake_alarm_step},.tag=ALARM_SERVICE_DESCRIPTOR_TAG,.descriptor_version=1,.output_modes=ALARM_MODE_VISUAL};
#define TEST_RESIDENT_IO() ((void)0)
#include "resident_telemetry_fixture.h"
static bool resident_retain(void){assert(!"Unexpected terminal custody");return false;}
static bool resident_acquire(const char*n,uint32_t v,uint64_t id,risc_runtime_capability_v1*g){
 g->slot=1;g->generation=1;
 if(!strcmp(n,"runtime.realtime")){g->api=&resident_clock;grants++;return true;}
 if(!strcmp(n,"telemetry.broadcast")){g->api=&resident_bt;grants++;return true;}
 if(!strcmp(n,"alarm.service")){assert(v==2);g->api=&resident_alarm;grants++;return true;}
 if(!strcmp(n,"input.navigation")){g->api=&nav_api;grants++;return true;}
 return fake_acquire(n,v,id,g);
}
static const risc_runtime_api_v1 runtime_api={.api_version=1,.struct_size=sizeof(runtime_api),.health=fake_health,.yield_ms=fake_yield,.diagnostic=fake_diag,.request_launch=fake_launch,.acquire=resident_acquire,.release=fake_release,.resident_shell=resident_get,.retain_invocation=resident_retain};
#else
static const risc_runtime_api_v1 runtime_api={.api_version=1,.struct_size=sizeof(runtime_api),.health=fake_health,.yield_ms=fake_yield,.diagnostic=fake_diag,.request_launch=fake_launch,.acquire=fake_acquire,.release=fake_release};
#endif
const risc_runtime_api_v1 *risc_runtime_get_api(uint32_t v){return v==1?&runtime_api:NULL;}
int main(int argc,char**argv){assert(argc>=2);directory=argv[1];memset(pixels,0xa5,sizeof(pixels));if(argc>2){FILE*f=fopen(argv[2],"r");assert(f);while(action_count<256&&fscanf(f,"%u %d %d",&actions[action_count].at,&actions[action_count].x,&actions[action_count].y)==3)action_count++;fclose(f);}uint8_t policy[]={0x51,1,3,0xa6};assert(fake_put(NULL,"quick_radio",policy,4)==0);
#ifdef HID_RENDER_WATCH_TOUCH
watch_touch=hid_watch_touch_start();assert(watch_touch);
#endif
#ifdef HID_RENDER_RUNTIME_DIAGNOSTICS
hid_serial_start();
#endif
assert(app_module_init()==0);app_main();app_module_fini();
#ifdef HID_RENDER_RUNTIME_DIAGNOSTICS
hid_serial_finish();
#endif
#ifdef HID_RENDER_WATCH_TOUCH
hid_watch_touch_stop();
#endif
assert(!grants&&!frames&&!subs&&!radio_owned&&!hid_owned&&!held_mod&&!held_key&&!held_mouse);
if(getenv("HID_RENDER_ACTIVE"))assert(hid_opens>=1&&hid_opens==hid_closes&&hid_polls>0);else assert(!hid_opens);
if(getenv("HID_RENDER_PAIR"))assert(allow_pair&&(paired_confirm||paired_reject)&&pairing_confirmations==1&&pairing_contacts>=1&&pairing_requests==1&&pairing_results==1);
if(getenv("HID_RENDER_PAIR_ACCEPT"))assert(paired_confirm&&!paired_reject);
if(getenv("HID_RENDER_PAIR_TIMEOUT")||getenv("HID_RENDER_PAIR_ERROR"))assert(!pairing_confirmations&&hid_opens==2&&hid_closes==2);
#ifdef HID_RENDER_RESIDENT
assert(resident_jump);
#endif
if(getenv("HID_RENDER_PAIR_REJECT"))assert(paired_reject&&!paired_confirm);
if(getenv("HID_RENDER_PAIR_MOVED"))assert(diagnostic_moved);
if(getenv("HID_RENDER_PAIR_MULTITOUCH"))assert(diagnostic_multitouch);
if(getenv("HID_RENDER_PAIR")&&getenv("HID_RENDER_GAP"))assert(diagnostic_gap);
if(getenv("HID_RENDER_MOUSE"))assert(hid_mouse_reports>=2);
if(getenv("HID_RENDER_TAP_DRAG"))assert(drag_moves>=2&&drag_releases==1&&!drag_held&&!hid_scroll_reports);
if(getenv("HID_RENDER_SCROLL_X"))assert(hid_scroll_reports>=2&&scroll_x>0&&!scroll_y);
if(getenv("HID_RENDER_SCROLL_Y"))assert(hid_scroll_reports>=2&&!scroll_x&&scroll_y<0);
if(getenv("HID_RENDER_SCROLL_FREE"))assert(hid_scroll_reports>=2&&scroll_x>0&&scroll_y<0);
if(getenv("HID_RENDER_MOUSE_RECONNECT"))assert(hid_opens==1&&hid_closes==1&&hid_mouse_reports>=3);
if(getenv("HID_RENDER_TRANSPORT_RECONNECT"))assert(hid_opens==2&&hid_closes==2&&diagnostic_transport&&diagnostic_closed);
if(getenv("HID_RENDER_LOW_BATTERY"))assert(hid_opens==1&&hid_closes==1&&low_battery_seen);
if(getenv("HID_RENDER_KEYS"))assert(hid_keyboard_reports>=2);
if(getenv("HID_RENDER_BACK"))assert(launches==1);
if(getenv("HID_RENDER_QUICK"))assert((paper_profile?radio_control_calls==0:radio_control_calls>=2)&&hid_closes==1);
if(getenv("HID_RENDER_GAP"))assert(gap_given&&hid_releases>=2);
if(getenv("HID_RENDER_ALARM"))assert(alarm_dismissed&&hid_opens==1&&hid_closes==1);
if(getenv("HID_RENDER_SLEEP"))assert(sleep_seen&&hid_opens==1&&hid_closes==1);
if(getenv("HID_RENDER_CLEANUP"))assert(close_attempts==2&&release_attempts==2&&unsub_attempts>=2);
if(getenv("HID_RENDER_HOME"))assert(launches==1&&!save_attempts);
if(getenv("HID_RENDER_SAVED")){assert(save_attempts==(getenv("HID_RENDER_SAVE_FAIL")?2u:1u));uint8_t saved[40];uint32_t count;assert(fake_get(NULL,"hid_buttons",saved,40,&count)==0&&count==40&&saved[6]==76);}
if(getenv("HID_RENDER_UNSAVED"))assert(!save_attempts);
assert(presents>0);
printf("HID production app/adapter: %u frames, %u polls; %u mouse/%u key reports; all grants released, neutral reports and stride guards verified\n",presents,polls,hid_mouse_reports,hid_keyboard_reports);return 0;}
