#include "bootstrap/Runtime.h"
#include "RiscDisplayOutputV1.h"
#include "RiscTouchV1.h"
#include "RiscInputNavigationV1.h"
#include "RiscPlatformClockV1.h"
#include "SceneKeyboardV1.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <vector>
static uint64_t us,begin_us,finish_us,next_scan,last_capture,max_capture_gap,action_digest=1469598103934665603ull;
static unsigned format=1;
static unsigned panel_ms,pixel_ns,period_ms,contacts,down_index,up_index,pattern,received,expected,frames,provider_polls,starts,stops;
static bool running,complete,held,pending,same_key;
static bool fingers[2];
static uint16_t finger_x[2];
static risc_touch_snapshot_v1 physical,reported;
static uint64_t present_us;
static unsigned transfer_slices;
static unsigned long long nanos;
static const risc_touch_api_v1*touch;
static uint8_t pixels[240*240*2];
extern "C" const risc_touch_api_v1*scene_timing_touch_start(void);
extern "C" const risc_touch_api_v1*scene_timing_touch_api(void);
extern "C" bool scene_timing_touch_quiesce(void);
extern "C" void scene_timing_touch_stop(void);
static unsigned duration(unsigned index){return pattern==2?period_ms*1000+20000:10000+index%4*5000;}
static void latch(){
 physical={};physical.width=240;physical.height=240;
 for(unsigned i=0;i<2;i++)if(fingers[i]){auto&c=physical.contacts[physical.contact_count++];c.id=(uint8_t)(i+1);c.x=finger_x[i];c.y=pattern>=3?18:97;}
 reported=physical;
}
extern "C" uint64_t scene_timing_us(){return us;}
extern "C" void scene_timing_advance(unsigned n){
 const uint64_t until=us+n;
 while(running){
  uint64_t down=down_index<contacts?begin_us+(uint64_t)down_index*period_ms*1000:UINT64_MAX;
  uint64_t up=up_index<contacts?begin_us+(uint64_t)up_index*period_ms*1000+duration(up_index):UINT64_MAX;
  uint64_t next=down<up?down:up;if(next_scan<next)next=next_scan;if(next>until)break;us=next;
  if(up==next){fingers[pattern==2?up_index%2:0]=false;++up_index;}
  if(down==next){unsigned id=pattern==2?down_index%2:0;fingers[id]=true;finger_x[id]=pattern>=3?(pattern%2?30:210):(same_key||down_index%2==0)?26:47;++down_index;}
  if(next_scan==next){latch();next_scan+=5000;}
 }
 us=until;
}
extern "C" void scene_timing_cpu_pixel(){nanos+=pixel_ns;unsigned n=(unsigned)(nanos/1000);nanos%=1000;if(n)scene_timing_advance(n);}
extern "C" void hid_renderer_watch_report(risc_touch_snapshot_v1*out){
 if(running){if(last_capture&&us-last_capture>max_capture_gap)max_capture_gap=us-last_capture;last_capture=us;}
 *out=reported;
}
extern "C" uint64_t hid_renderer_watch_millis(){return us/1000;}
extern "C" unsigned scene_timing_mode(){return pattern;}
extern "C" void scene_timing_begin(){running=true;begin_us=us+10000;next_scan=begin_us+2500;finish_us=begin_us+(uint64_t)contacts*period_ms*1000+100000;}
extern "C" bool scene_timing_finished(){return us>=finish_us;}
static uint64_t hash(uint64_t h,uint64_t v){for(unsigned i=0;i<8;i++){h^=(uint8_t)v;h*=1099511628211ull;v>>=8;}return h;}
extern "C" void scene_timing_action(unsigned key){
 if(expected){unsigned wanted=pattern==3?RISC_SCENE_KEY_CANCEL:pattern==4||pattern==6?256:pattern==5?257:(same_key||received%2==0?'Q':'W');assert(key==wanted);const unsigned release=duration(received);assert(us>=begin_us+(uint64_t)received*period_ms*1000+release);assert(us-begin_us-(uint64_t)received*period_ms*1000-release<20000);}
 action_digest=hash(hash(action_digest,key),us-begin_us);++received;
}
extern "C" void scene_timing_complete(unsigned count){assert(count==received);if(expected)assert(count==contacts);else assert(count<contacts);complete=true;running=false;}
static bool info(void*,risc_display_info_v1*out){*out={};out->api_version=1;out->struct_size=sizeof(*out);out->width=240;out->height=240;out->supported_formats=RISC_DISPLAY_FORMAT_BIT(format);out->preferred_format=format;return true;}
static bool acquire(void*,uint32_t f,risc_display_surface_v1*out){assert(!held&&!pending&&f==format);held=true;const unsigned stride=format==5?480:30;*out={frames+1,pixels,240,240,stride,stride*240,format};return true;}
static void release(void*,uint64_t f){assert(held&&f);held=false;}
static bool submit(void*,uint64_t f,const risc_display_rect_v1*,size_t n,const risc_display_present_options_v1*,uint64_t*out){assert(held&&!pending&&f&&!n);held=false;pending=true;present_us=us;transfer_slices=4;*out=++frames;return true;}
static bool status(void*,uint64_t f,risc_display_present_status_v1*out){assert(!held&&f);if(pending&&!transfer_slices&&us-present_us>=(uint64_t)panel_ms*1000)pending=false;out->state=pending?RISC_DISPLAY_PRESENT_ACTIVE:RISC_DISPLAY_PRESENT_COMPLETE;return true;}
static const risc_display_output_api_v1 display={1,sizeof(display),nullptr,info,acquire,release,submit,status,nullptr,nullptr};
static bool navpoll(void*,risc_input_navigation_frame_v1*out){*out={};return true;}
static bool foreground(void*,const risc_input_foreground_v1*,size_t){return true;}
static bool reset(void*){return true;}
static const risc_input_navigation_api_v1 navigation={1,sizeof(navigation),nullptr,navpoll,foreground,reset};
static uint64_t now(void*){return us/1000;}
static void sleep(void*,uint32_t n){scene_timing_advance(n*1000);}
static const risc_platform_clock_api_v1 clock_api={1,sizeof(clock_api),nullptr,now,sleep};
extern "C" const void*scene_timing_provider(const char*name){if(!strcmp(name,"display.output"))return &display;if(!strcmp(name,"input.navigation"))return &navigation;if(!strcmp(name,"input.touch.raw")){return scene_timing_touch_api();}assert(0);return nullptr;}
extern "C" bool scene_timing_provider_event(const char*name,unsigned event){if(event==1){++starts;if(!strcmp(name,"input.touch.raw"))touch=scene_timing_touch_start();}else if(event==2){++stops;if(!strcmp(name,"input.touch.raw"))scene_timing_touch_stop();}else if(event==3){if(!strcmp(name,"input.touch.raw"))return scene_timing_touch_quiesce();if(!strcmp(name,"display.output"))return !held&&!pending;}return true;}
extern "C" void scene_timing_provider_poll(const char*name,uint32_t budget){++provider_polls;if(!strcmp(name,"display.output")&&pending&&transfer_slices){assert(budget>=2);scene_timing_advance(2000);--transfer_slices;}}
int main(int argc,char**argv){assert(argc==9);format=atoi(argv[8]);assert(format==1||format==5);panel_ms=atoi(argv[2]);pixel_ns=atoi(argv[3]);period_ms=atoi(argv[4]);contacts=atoi(argv[5]);pattern=atoi(argv[6]);same_key=pattern==1;expected=atoi(argv[7]);
 RiscBoot::Port port{[](){return true;},[](risc_runtime_health_v1*h){h->uptime_ms=(uint32_t)(us/1000);return true;},[](uint32_t n){scene_timing_advance(n*1000);},[](const char*){return true;}};
 port.bindPlatforms=[](RiscBoot::Runtime&r){return r.registerPlatform("platform.clock",1,RiscBoot::Runtime::Scope::Global,0,&clock_api);};
 auto runtime=std::make_unique<RiscBoot::Runtime>(port);assert(runtime->prepare(argv[1]));bool ok=runtime->run();if(!ok)fprintf(stderr,"Runtime: %s\n",runtime->error());assert(ok&&complete&&!held&&!pending);runtime.reset();assert(starts==stops);
 printf("watch-FT6336U-runtime format=%u panel=%u pixel-ns=%u period=%u contacts=%u pattern=%u received=%u max-poll-us=%llu frames=%u provider-polls=%u digest=%016llx\n",format,panel_ms,pixel_ns,period_ms,contacts,pattern,received,(unsigned long long)max_capture_gap,frames,provider_polls,(unsigned long long)action_digest);
}
