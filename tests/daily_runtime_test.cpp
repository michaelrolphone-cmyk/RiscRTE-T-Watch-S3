// Real Runtime, independently loaded physical Watch drivers and unmodified shared
// applications. Reuse the GUI suite's raw GPIO/I2C/SPI model, never an app API mock.
#define main watch_gui_test_main
#define watch_test_loading watch_gui_loading
#define watch_test_unloading watch_gui_unloading
#include "launcher_runtime_test.cpp"
#undef watch_test_unloading
#undef watch_test_loading
#undef main
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include <ctime>

namespace {
enum Scenario { CalculatorTouch, CalculatorCrown, StartSleep, RecoverPause,
                PausedReboot, InvalidRtc, BackwardRtc, LostRtc, ReadFailure,
                WriteFailure, PauseFailure, CorruptRecord };
struct Persistent { uint8_t bytes[20]; uint32_t size, writes; } *saved;
struct Daily {
 Scenario scenario; uint32_t wall; unsigned drivers=0,unloads=0,reads=0,puts=0;
 unsigned appLoads=0,checks=0; bool terminal=false,sawArithmetic=false;
 uint32_t displayed=0; std::vector<std::string> sequence;
} d;
uint32_t read32(const uint8_t*p) { return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24); }
uint32_t checksum(const uint8_t*p) {uint32_t n=2166136261u;for(unsigned i=0;i<16;++i)n=(n^p[i])*16777619u;return n;}
void write32(uint8_t*p,uint32_t n) {for(unsigned i=0;i<4;++i){p[i]=(uint8_t)n;n>>=8;}}
void seedRunning(uint32_t anchor) {
 *saved=Persistent{};saved->size=20;memcpy(saved->bytes,"SW01\1\0\0\0",8);
 write32(saved->bytes+12,anchor);write32(saved->bytes+16,checksum(saved->bytes));
}
bool calculatorScenario() {return d.scenario==CalculatorTouch||d.scenario==CalculatorCrown;}
bool dailyLive(risc_runtime_health_v1*h) {
 assert(++m.calls<200000);h->uptime_ms=(uint32_t)m.time;
 if(d.scenario==StartSleep)return true;
 return m.clockReady<2;
}
void dailyDelay(uint32_t ms) {m.time+=ms;assert(m.time<25000);}
bool dailyLog(const char*s) {
 puts(s);assert(!strstr(s,"error="));
 if(!strncmp(s,"WATCH_CLOCK ready",17)) {
  ++m.clockReady;m.clock_ready=true;m.clock_ready_at=m.time;
  if(m.app=="clock.elf")assert(m.time-m.app_start<300);
 }
 return true;
}
uint8_t bcd(unsigned n) {return (uint8_t)((n/10)*16+n%10);}
void calendar() {
 // Raw RTC is UTC+08 by deployment policy. Stopwatch must use these raw
 // calendar seconds, never the Clock's Denver display conversion.
 std::time_t unixTime=(std::time_t)946684800+d.wall+(uint32_t)(m.time/1000);
 std::tm t{};assert(gmtime_r(&unixTime,&t));
 const uint8_t raw[]={bcd((unsigned)t.tm_sec),bcd((unsigned)t.tm_min),bcd((unsigned)t.tm_hour),
   bcd((unsigned)t.tm_mday),(uint8_t)t.tm_wday,bcd((unsigned)t.tm_mon+1),bcd((unsigned)t.tm_year-100)};
 memcpy(m.registers[1]+2,raw,sizeof(raw));
 if(m.app=="stopwatch.elf"&&d.scenario==InvalidRtc)m.registers[1][2]|=0x80;
}
bool tap(uint8_t*rx,unsigned age,unsigned start,unsigned x,unsigned y) {
 if(age>=start&&age<start+70){contact(rx,x,y);return true;}return false;
}
bool dailyI2c(uint8_t p,uint8_t a,const uint8_t*tx,size_t tn,uint8_t*rx,size_t rn,uint32_t ms) {
 const unsigned age=(unsigned)(m.time-m.app_start);
 if(p) {
  assert(m.bus[p]&&a==0x38&&tn==1&&tx[0]==2&&rn==13);memset(rx,0,rn);++m.touchReads;
  if(m.app=="default.elf"&&!d.terminal&&m.clock_ready&&m.time-m.clock_ready_at>=20)
   contact(rx,m.time-m.clock_ready_at<60?120:160,120);
  else if(m.app=="springboard.elf"&&m.springLoads==1) {
   if(age<120)contact(rx,160+age/12,120);
   else tap(rx,age,1500,147,calculatorScenario()?166:73);
  } else if(m.app=="calculator.elf") {
   // 12.5 + 7.25 = 19.75 through real touch down/release transitions.
   const unsigned xy[][2]={{33,190},{91,190},{91,219},{91,161},{207,190},
                          {33,131},{91,219},{91,190},{91,161},{178,219}};
   for(unsigned i=0;i<sizeof(xy)/sizeof(*xy);++i)tap(rx,age,180+i*200,xy[i][0],xy[i][1]);
   if(d.scenario==CalculatorTouch)tap(rx,age,2500,20,18);
  } else if(m.app=="stopwatch.elf") {
   if(d.scenario!=PausedReboot&&d.scenario!=CorruptRecord&&d.scenario!=RecoverPause)
    tap(rx,age,180,60,176);
   if(d.scenario==RecoverPause||d.scenario==PauseFailure)tap(rx,age,1300,60,176);
   tap(rx,age,2700,20,18);
  }
  return true;
 }
 if(a==0x51&&tx[0]==2&&rn==7) {
  calendar();
  if(m.app=="stopwatch.elf"&&d.scenario==LostRtc&&age>=800)return false;
 }
 if(a==0x34&&tx[0]==0x49&&rn==1&&!m.keys_in_app) {
  bool back=(m.app=="springboard.elf"&&m.springLoads==2&&age>=400)||
            (m.app=="calculator.elf"&&d.scenario==CalculatorCrown&&age>=2500)||
            (m.app=="clock.elf"&&d.scenario==StartSleep&&m.clock_ready&&m.time-m.clock_ready_at>=300);
  if(back){m.registers[0][0x49]|=8;++m.keys_in_app;++m.crown_events;}
 }
 return i2cTransfer(p,a,tx,tn,rx,rn,ms);
}
int32_t dailyGet(void*,uint32_t ns,const char*key,void*data,uint32_t capacity,uint32_t*size) {
 *size=0;
 if(ns==1) {
  if((!strcmp(key,"watch_face")||!strcmp(key,"time_format")))return RISC_KEY_VALUE_NOT_FOUND;
  assert(!strcmp(key,"sleep_mode")&&(m.app=="default.elf"||m.app=="clock.elf"));
  if(d.scenario==StartSleep){assert(capacity>=4);memcpy(data,"\x53\x01\x01\xa4",4);*size=4;return 0;}
  return RISC_KEY_VALUE_NOT_FOUND;
 }
 assert(ns==2&&!strcmp(key,"stopwatch")&&m.app=="stopwatch.elf");++d.reads;
 if(d.scenario==ReadFailure)return RISC_KEY_VALUE_IO;
 if(!saved->size)return RISC_KEY_VALUE_NOT_FOUND;
 assert(capacity>=saved->size);memcpy(data,saved->bytes,saved->size);*size=saved->size;return 0;
}
int32_t dailyPut(void*,uint32_t ns,const char*key,const void*data,uint32_t size) {
 assert(ns==2&&!strcmp(key,"stopwatch")&&m.app=="stopwatch.elf"&&size==20);++d.puts;
 const auto*p=(const uint8_t*)data;
 assert(!memcmp(p,"SW01",4)&&read32(p+16)==checksum(p)&&p[4]<=1&&p[5]<=1&&!p[6]&&!p[7]);
 if(d.scenario==WriteFailure||(d.scenario==PauseFailure&&d.puts==2))return RISC_KEY_VALUE_IO;
 memcpy(saved->bytes,data,size);saved->size=size;++saved->writes;return 0;
}
const RiscBoot::KeyValueBackend dailyKv={nullptr,dailyGet,dailyPut};

// Independent pixel oracle. All observations are decoded from the final raw
// SPI RGB565 panel frame, downstream of app, adapter, Runtime and real driver.
const uint8_t digits[10][5]={{62,81,73,69,62},{0,66,127,64,0},{98,81,73,73,70},
 {34,65,73,73,54},{24,20,18,127,16},{39,69,69,69,57},{60,74,73,73,48},
 {1,113,9,5,3},{54,73,73,73,54},{6,73,73,41,30}};
const uint8_t letters[26][5]={{126,9,9,9,126},{127,73,73,73,54},{62,65,65,65,34},
 {127,65,65,34,28},{127,73,73,73,65},{127,9,9,9,1},{62,65,73,73,58},
 {127,8,8,8,127},{0,65,127,65,0},{32,64,65,63,1},{127,8,20,34,65},
 {127,64,64,64,64},{127,2,12,2,127},{127,4,8,16,127},{62,65,65,65,62},
 {127,9,9,9,6},{62,65,81,33,94},{127,9,25,41,70},{70,73,73,73,49},
 {1,1,127,1,1},{63,64,64,64,63},{31,32,64,32,31},{127,32,24,32,127},
 {99,20,8,20,99},{3,4,120,4,3},{97,81,73,69,67}};
bool black(unsigned x,unsigned y) {
 assert(x<240&&y<240);unsigned p=2*(240*y+x);assert(m.frame[p]==m.frame[p+1]);
 assert(m.frame[p]==0||m.frame[p]==255);return m.frame[p]==0;
}
bool glyph(int x,int y,char c,unsigned scale,bool small=false) {
 for(unsigned col=0;col<5;++col) {
  unsigned bits=c>='0'&&c<='9'?digits[c-'0'][col]:c>='A'&&c<='Z'?letters[c-'A'][col]:
   c=='-'?8:c=='.'?(col==1||col==2?96:0):c==':'?(small?(col==2?36:0):(col==1||col==2?54:0)):0;
  for(unsigned row=0;row<7;++row)for(unsigned dx=0;dx<scale;++dx)for(unsigned dy=0;dy<scale;++dy)
   if(black(x+col*scale+dx,y+row*scale+dy)!=((bits&(1u<<row))!=0))return false;
 }return true;
}
void label(const char*expected,int y) {
 const int n=(int)strlen(expected),x=4+(232-n*6)/2;
 for(int i=0;i<n;++i)assert(glyph(x+i*6,y,expected[i],1,true));
}
uint32_t duration() {
 char out[12]={0};const int x=(240-(11*6-1)*3)/2;
 for(unsigned i=0;i<11;++i) {
  if(i==2||i==5||i==8){out[i]=i==8?'.':':';assert(glyph(x+i*18,64,out[i],3));continue;}
  bool found=false;for(char c='0';c<='9';++c)if(glyph(x+i*18,64,c,3)){out[i]=c;found=true;break;}
  assert(found);
 }
 unsigned hours=(out[0]-'0')*10+out[1]-'0',minutes=(out[3]-'0')*10+out[4]-'0';
 unsigned seconds=(out[6]-'0')*10+out[7]-'0',centis=(out[9]-'0')*10+out[10]-'0';
 assert(minutes<60&&seconds<60);return ((hours*60+minutes)*60+seconds)*1000+centis*10;
}
void inspectApp() {
 assert(m.frame_rows==240&&m.frames_in_app>0);++d.checks;
 if(calculatorScenario()) {
  const char*expected="19.75";const int x=240-8-(5*6-1)*4;
  for(unsigned i=0;i<5;++i)assert(glyph(x+i*24,42,expected[i],4));
  d.sawArithmetic=true;assert(!d.reads&&!d.puts);return;
 }
 d.displayed=duration();
 switch(d.scenario) {
 case StartSleep:label("RUNNING",105);assert(d.displayed>=2000&&d.displayed<3000&&saved->bytes[4]==1&&d.puts==1);break;
 case RecoverPause:label("PAUSED",105);label("PAUSED - APPROXIMATE",124);assert(d.displayed>=600000&&d.displayed<620000&&d.displayed==read32(saved->bytes+8)/10*10&&saved->bytes[4]==0&&saved->bytes[5]==1&&d.puts==1);break;
 case PausedReboot:label("PAUSED",105);assert(d.displayed==read32(saved->bytes+8)/10*10&&!d.puts);break;
 case InvalidRtc:label("PAUSED",105);label("RTC UNAVAILABLE - RETRY",124);assert(!d.displayed&&!d.puts);break;
 case BackwardRtc:label("PAUSED",105);label("RETRY OR RESET REQUIRED",124);assert(!d.displayed&&!d.puts&&saved->bytes[4]==1);break;
 case LostRtc:label("PAUSED",105);label("RTC LOST - SAVE PAUSE",124);assert(d.displayed>=700&&d.displayed<1300&&d.puts==1&&saved->bytes[4]==1);break;
 case ReadFailure:label("STORAGE ERROR",105);label("RETRY OR RESET REQUIRED",124);assert(!d.displayed&&!d.puts);break;
 case WriteFailure:label("PAUSED",105);label("SAVE UNCONFIRMED - RETRY",124);assert(!d.displayed&&d.puts==1&&!saved->size);break;
 case PauseFailure:label("RUNNING",105);label("SAVE UNCONFIRMED - RETRY",124);assert(d.displayed>=2000&&d.puts==2&&saved->writes==1&&saved->bytes[4]==1);break;
 case CorruptRecord:label("STORAGE ERROR",105);label("SAVED DATA INVALID",124);assert(!d.displayed&&!d.puts);break;
 default:assert(false);
 }
}
bool dailyDeepValid(uint8_t pin){assert(pin==21);return true;}
bool dailyDeepReady(){assert(!m.held&&!m.levels[45]&&m.pad_held);return true;}
bool dailyDeepArm(uint8_t pin,bool high,bool pullup){assert(pin==21&&!high&&pullup);++m.sleep_attempts;return true;}
bool dailyDeepClear(uint8_t pin,bool pullup){assert(pin==21&&pullup);return true;}
bool dailyDeepHold(uint8_t pin,bool enabled){assert(pin==45&&!m.levels[45]);m.pad_held=enabled;return true;}
void dailyDeepEnter() {
 assert(d.scenario==StartSleep&&m.app=="clock.elf"&&m.clockReady==2&&d.checks==1&&d.drivers==7);
 const std::vector<std::string> expected={"default.elf","springboard.elf","stopwatch.elf","springboard.elf","clock.elf"};
 assert(d.sequence==expected&&d.unloads==4&&m.bus[0]&&m.bus[1]&&m.spi);
 assert(m.sleep_attempts==1&&m.pad_held&&!m.levels[45]&&m.frame_rows==240&&!m.dateWrites);
 assert(saved->size==20&&saved->bytes[4]==1&&saved->writes==1);
 assert(m.registers[0][0x40]==0&&m.registers[0][0x41]==8&&m.registers[0][0x42]==0);
 for(uint8_t value:m.frame)assert(value==0);
 fprintf(stderr,"Daily Stopwatch -> Springboard -> Clock -> real deep entry PASS; KV retained for cold boot\n");
 _exit(77); // Model the non-returning reset boundary. No app/claim state survives.
}
void run(const char*root,Scenario scenario,uint32_t wall) {
 m=Model{};d=Daily{};d.scenario=scenario;d.wall=wall;m.registers[0][3]=0x4a;
 m.registers[0][0x34]=0x0f;m.registers[0][0x35]=0xa0;calendar();
 RiscCpu::Hardware hw={owner,now,dailyDelay,gpioOpen,gpioWrite,gpioRead,gpioPwm,gpioClose,
   i2cOpen,dailyI2c,i2cClose,spiOpen,spiBegin,spiTransfer,spiEnd,spiClose};
 hw.deepWakeValid=dailyDeepValid;hw.deepReady=dailyDeepReady;hw.deepWakeArm=dailyDeepArm;
 hw.deepWakeClear=dailyDeepClear;hw.deepSleep=dailyDeepEnter;hw.deepHold=dailyDeepHold;
 RiscCpu::Port port(hw);cpu=&port;
 RiscBoot::Runtime runtime({owner,dailyLive,dailyDelay,dailyLog,bind,&dailyKv,[](){return cpu->appExitSafe();}});
 if(!runtime.prepare(root)||!runtime.run()){fprintf(stderr,"Daily Runtime failure: %s\n",runtime.error());assert(false);}
 const std::vector<std::string> expected={"default.elf","springboard.elf",calculatorScenario()?"calculator.elf":"stopwatch.elf","springboard.elf","clock.elf","default.elf"};
 assert(d.sequence==expected&&d.drivers==7&&d.unloads==13&&d.checks==1&&m.clockReady==2);
 assert(d.sawArithmetic==calculatorScenario());
 assert(m.retained_checks==2&&m.touchReads>40&&m.rows>240&&m.pwm>=1&&!m.dateWrites);
 assert(!m.bus[0]&&!m.bus[1]&&!m.spi&&!m.held&&!m.pad_held&&port.quiescent()&&port.appExitSafe());
 for(bool pin:m.pins)assert(!pin);
 fprintf(stderr,"Daily real Runtime scenario=%u PASS frames=%u elapsed=%u ns2-gets=%u puts=%u; all resources quiescent\n",scenario,m.rows/240,d.displayed,d.reads,d.puts);
}
}
extern "C" void watch_test_unloading(){++d.unloads;}
extern "C" void watch_test_loading(const char*path) {
 const char*name=strrchr(path,'/');name=name?name+1:path;
 if(!strcmp(name,"driver.elf")){++d.drivers;return;}
 if(m.app=="calculator.elf"||m.app=="stopwatch.elf")inspectApp();
 if(!strcmp(name,"springboard.elf")) {
  assert(m.frame_rows==240);memcpy(m.retained_clock,m.frame,sizeof(m.frame));++m.springLoads;
 }
 if(!strcmp(name,"default.elf")&&m.clockReady==2)d.terminal=true;
 m.previous_app=m.app;m.app=name;m.app_start=m.time;m.frames_in_app=0;m.clock_ready=false;m.keys_in_app=0;
 d.sequence.emplace_back(name);++d.appLoads;
 fprintf(stderr,"Daily load %s at %llu ms\n",name,(unsigned long long)m.time);
}
int main(int argc,char**argv) {
 assert(argc==2);void*region=mmap(nullptr,sizeof(Persistent),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
 assert(region!=MAP_FAILED);saved=(Persistent*)region;*saved=Persistent{};
 // 2026-10-04 00:40 raw PCF calendar, deliberately different from Denver.
 const uint32_t wall=844389600u;
 run(argv[1],CalculatorTouch,wall);run(argv[1],CalculatorCrown,wall);
 pid_t child=fork();assert(child>=0);if(!child){run(argv[1],StartSleep,wall);_exit(1);}
 int status=0;assert(waitpid(child,&status,0)==child&&WIFEXITED(status)&&WEXITSTATUS(status)==77);
 assert(saved->size==20&&saved->bytes[4]==1&&saved->writes==1);
 assert(read32(saved->bytes+12)>=wall&&read32(saved->bytes+12)<wall+20);
 run(argv[1],RecoverPause,wall+610);const uint32_t paused=read32(saved->bytes+8);assert(saved->writes==2);
 run(argv[1],PausedReboot,wall+1210);assert(read32(saved->bytes+8)==paused&&saved->writes==2);
 for(Scenario s:{InvalidRtc,ReadFailure,WriteFailure,LostRtc,PauseFailure,CorruptRecord,BackwardRtc}) {
  *saved=Persistent{};
  if(s==BackwardRtc)seedRunning(wall+300);
  if(s==CorruptRecord){seedRunning(wall);saved->bytes[16]^=1;}
  run(argv[1],s,wall);
 }
 assert(munmap(region,sizeof(Persistent))==0);
 puts("Daily apps: production touch, arithmetic, crown, true deep reset, raw RTC recovery, persisted pause, visible failures, namespace 2 and lifecycle PASS");
 return 0;
}
