// Exact Runtime/Watch providers and real shared apps. Only raw hardware is modeled.
#define main watch_gui_test_main
#define watch_test_loading watch_hybrid_gui_loading
#define watch_test_unloading watch_hybrid_gui_unloading
#include "launcher_runtime_test.cpp"
#undef watch_test_unloading
#undef watch_test_loading
#undef main
#include <sys/wait.h>
#include <unistd.h>
#include <ctime>
namespace {
enum Case { GpioWake, TimerCrown, TimerFalling, CrownDuringHold, TimerDeep, LightRefusal,
            TimerCleanupFailure, InputCleanupFailure, DeepReturned, DeepRefusal, RepeatWake, CrownDuringDiagnostic };
struct Hybrid {
 Case test;unsigned target,drivers=0,unloads=0,entries=0,deep=0,restores=0,idles=0,timers=0,timerClears=0,inputClears=0,puts=0;
 uint32_t duration=0;uint64_t sleepAt=0,wokeAt=0,startedAt=0;bool timer=false,input=false,done=false,inSleep=false;
 uint8_t savedFrame[240*240*2]{},record[20]{};unsigned recordSize=0;
 std::vector<std::string> sequence;
} h;
const char* targets[]={"default.elf","springboard.elf","battery.elf","settings.elf","calculator.elf","stopwatch.elf"};
bool active(){return m.app==targets[h.target];}
uint8_t bcd(unsigned n){return (uint8_t)((n/10)*16+n%10);}
void rtcTime(){std::time_t value=946684800+844389600+(std::time_t)(m.time/1000);std::tm t{};assert(gmtime_r(&value,&t));
 uint8_t raw[]={bcd(t.tm_sec),bcd(t.tm_min),bcd(t.tm_hour),bcd(t.tm_mday),(uint8_t)t.tm_wday,bcd(t.tm_mon+1),bcd(t.tm_year-100)};memcpy(m.registers[1]+2,raw,7);}
bool liveHybrid(risc_runtime_health_v1*out){assert(++m.calls<1000000);out->uptime_ms=(uint32_t)m.time;return !h.done;}
void delayHybrid(uint32_t ms){m.time+=ms;assert(m.time<1500000);}
bool touchTap(uint8_t*rx,unsigned age,unsigned when,unsigned x,unsigned y){if(age>=when&&age<when+70){contact(rx,x,y);return true;}return false;}
bool i2cHybrid(uint8_t p,uint8_t a,const uint8_t*tx,size_t tn,uint8_t*rx,size_t rn,uint32_t ms){
 unsigned age=(unsigned)(m.time-m.app_start);
 if(p){assert(a==0x38&&tn==1&&tx[0]==2&&rn==13);memset(rx,0,rn);++m.touchReads;
  if(!h.target)return true;
  if(m.app=="default.elf"&&m.clock_ready&&m.time-m.clock_ready_at>=20)contact(rx,m.time-m.clock_ready_at<60?120:160,120);
  else if(m.app=="springboard.elf"&&h.target>1){
   if(age<120)contact(rx,160+age/12,120);
   else touchTap(rx,age,1500,h.target==2||h.target==3?93:147,h.target==2||h.target==4?166:73);
  } else if(m.app=="calculator.elf") {
   const unsigned xy[][2]={{33,190},{91,190},{91,219},{91,161},{207,190},{33,131},{91,219},{91,190},{91,161}};
   if(!h.entries)for(unsigned i=0;i<9;i++)touchTap(rx,age,180+i*200,xy[i][0],xy[i][1]);
   if(h.restores && ((h.test!=RepeatWake&&h.test!=LightRefusal) || h.entries>=2))touchTap(rx,(unsigned)(m.time-h.wokeAt),180,178,219);
  } else if(m.app=="stopwatch.elf"&&!h.entries)touchTap(rx,age,180,60,176);
  return true;
 }
 if(a==0x51&&tx[0]==2&&rn==7)rtcTime();
 if(a==0x34&&tx[0]==0x49&&rn==1&&!h.target&&m.clock_ready&&!m.keys_in_app&&m.time-m.clock_ready_at>=300){m.registers[0][0x49]|=8;++m.keys_in_app;}
 bool was=m.clock_ready;m.clock_ready=false;bool result=i2cTransfer(p,a,tx,tn,rx,rn,ms);m.clock_ready=was;
 if(a==0x34)m.levels[21]=(m.registers[0][0x49]&m.registers[0][0x41])==0;
 return result;
}
int32_t getHybrid(void*,uint32_t ns,const char*key,void*out,uint32_t cap,uint32_t*size){*size=0;
 if(ns==1){if((!strcmp(key,"watch_face")||!strcmp(key,"time_format")))return RISC_KEY_VALUE_NOT_FOUND;assert(!strcmp(key,"sleep_mode")&&(m.app=="default.elf"||m.app=="clock.elf"||m.app=="settings.elf"));return RISC_KEY_VALUE_NOT_FOUND;}
 assert(ns==2&&m.app=="stopwatch.elf"&&!strcmp(key,"stopwatch"));
 if(!h.recordSize)return RISC_KEY_VALUE_NOT_FOUND;
 assert(cap>=h.recordSize);memcpy(out,h.record,h.recordSize);*size=h.recordSize;return 0;
}
int32_t putHybrid(void*,uint32_t ns,const char*key,const void*data,uint32_t size){assert(ns==2&&m.app=="stopwatch.elf"&&!strcmp(key,"stopwatch")&&size==20);h.puts++;h.recordSize=size;memcpy(h.record,data,size);return 0;}
const RiscBoot::KeyValueBackend hybridKv={nullptr,getHybrid,putHybrid};
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

void verifyPreserved(){
 if(h.target==4){const char*expected="19.75";int x=240-8-(5*6-1)*4;for(unsigned i=0;i<5;i++)if(!glyph(x+i*24,42,expected[i],4)){
   fprintf(stderr,"Calculator mismatch case=%u entry=%u restores=%u time=%llu wake=%llu\n",h.test,h.entries,h.restores,(unsigned long long)m.time,(unsigned long long)h.wokeAt);
   assert(false);
  }}
 if(h.target==5){label("RUNNING",105);label("RUNNING",124);uint32_t value=duration();
  assert(value>=m.time-h.startedAt-80 && value<=m.time-h.startedAt);assert(h.puts==1&&h.record[4]==1&&h.record[5]==0);}
}
bool logHybrid(const char*s){puts(s);
 if(h.test==CrownDuringDiagnostic&&!strcmp(s,"WATCH_SLEEP phase=deep timer=expired"))m.registers[0][0x49]|=2;
 if(!strncmp(s,"WATCH_CLOCK ready",17)){m.clockReady++;m.clock_ready=true;m.clock_ready_at=m.time;}
 if(!strcmp(s,"PORTABLE_APP sleep=idle")){assert(active());h.inSleep=true;++h.idles;memcpy(h.savedFrame,m.frame,sizeof(m.frame));}
 if(!strcmp(s,"PORTABLE_APP sleep=resumed")||!strcmp(s,"PORTABLE_APP sleep=refused")){
  assert(active()&&!h.timer&&!h.input);h.inSleep=false;assert(!memcmp(h.savedFrame,m.frame,sizeof(m.frame)));++h.restores;h.wokeAt=m.time;
 }
 return true;
}
bool validWake(uint8_t p){assert(p==21);return true;}
bool wakeArmHybrid(uint8_t p,bool level){assert(p==21&&!level&&!h.input);h.input=true;return true;}
bool wakeClearHybrid(uint8_t p){assert(p==21);h.inputClears++;if(h.test==InputCleanupFailure)return false;h.input=false;return true;}
bool timerArmHybrid(uint32_t ms){assert(ms==300000&&!h.timer);h.timer=true;h.duration=ms;h.timers++;return true;}
bool timerClearHybrid(){h.timerClears++;if(h.test==TimerCleanupFailure)return false;h.timer=false;return true;}
bool lightHybrid(uint32_t*cause){
 assert(active()&&h.timer&&h.input&&h.duration==300000&&!m.held&&!m.levels[45]);
 assert(m.registers[0][0x40]==0&&m.registers[0][0x41]==8&&m.registers[0][0x42]==0);
 for(uint8_t v:m.frame)assert(!v);
 if(h.target)assert(m.time-m.app_start>=60000);
 h.sleepAt=m.time;h.entries++;
 if(h.test==LightRefusal&&h.entries==1){*cause=RISC_LIGHT_SLEEP_WAKE_TIMER;return false;}
 bool timer=h.test!=GpioWake&&h.test!=LightRefusal&&h.test!=RepeatWake&&h.test!=TimerCleanupFailure&&h.test!=InputCleanupFailure;
 m.time+=timer?300000:123457;
 *cause=timer?RISC_LIGHT_SLEEP_WAKE_TIMER:RISC_LIGHT_SLEEP_WAKE_GPIO;
 if(!timer||h.test==TimerCrown){m.registers[0][0x49]|=8;m.levels[21]=false;}
 if(h.test==TimerFalling)m.registers[0][0x49]|=2;
 return true;
}
bool holdHybrid(uint8_t p,bool on){assert(p==45&&!m.levels[45]);m.pad_held=on;
 if(on&&h.test==CrownDuringHold)m.registers[0][0x49]|=2;
 return true;
}
bool deepReadyHybrid(){assert(!m.held&&!m.levels[45]&&m.pad_held);return true;}
bool deepArmHybrid(uint8_t p,bool high,bool pull){assert(p==21&&!high&&pull);h.deep++;return h.test!=DeepRefusal;}
bool deepClearHybrid(uint8_t p,bool pull){assert(p==21&&pull);return true;}
void enterDeepHybrid(){assert(active()&&h.entries==1&&h.deep==1&&!h.restores&&!h.timer&&!h.input&&m.pad_held);
 assert(m.time-h.sleepAt==300000);for(uint8_t value:m.frame)assert(!value);
 assert(h.drivers==7&&h.unloads==h.sequence.size()-1);
 if(h.test==DeepReturned)return;
 assert(h.test==TimerDeep);_exit(77);
}
bool spiHybrid(uint8_t p,const uint8_t*t,uint8_t*r,size_t n,uint32_t ms){
 bool result=spiTransfer(p,t,r,n,ms);
 if(active()&&h.target==5&&h.puts==1&&!h.startedAt)h.startedAt=m.time;
 return result;
}
void stepCheck(){
 if(h.target&&h.restores&&!h.inSleep&&m.time-h.wokeAt>=500){
  if((h.test==RepeatWake||h.test==LightRefusal)&&h.entries<2)return;
  verifyPreserved();h.done=true;
 }
 if(!h.target&&h.entries&&m.time-h.sleepAt>123957&&h.test!=RepeatWake)h.done=true;
}
void delayCheck(uint32_t ms){delayHybrid(ms);stepCheck();}
void runHybrid(const char*root,unsigned target,Case test){
 m=Model{};h=Hybrid{};h.target=target;h.test=test;m.registers[0][3]=0x4a;m.registers[0][0x49]=8;
 m.registers[0][0x34]=0x0f;m.registers[0][0x35]=0xa0;rtcTime();
 RiscCpu::Hardware hw={owner,now,delayCheck,gpioOpen,gpioWrite,gpioRead,gpioPwm,gpioClose,i2cOpen,i2cHybrid,i2cClose,spiOpen,spiBegin,spiHybrid,spiEnd,spiClose};
 hw.wakeValid=validWake;hw.wakeArm=wakeArmHybrid;hw.wakeClear=wakeClearHybrid;hw.lightSleep=lightHybrid;
 hw.timerArm=timerArmHybrid;hw.timerClear=timerClearHybrid;hw.deepWakeValid=validWake;hw.deepReady=deepReadyHybrid;
 hw.deepWakeArm=deepArmHybrid;hw.deepWakeClear=deepClearHybrid;hw.deepSleep=enterDeepHybrid;hw.deepHold=holdHybrid;
 RiscCpu::Port port(hw);cpu=&port;RiscBoot::Runtime runtime({owner,liveHybrid,delayCheck,logHybrid,bind,&hybridKv,[](){return cpu->appExitSafe();}});
 assert(runtime.prepare(root));bool ok=runtime.run();
 bool retained=test==TimerCleanupFailure||test==InputCleanupFailure||test==DeepReturned;
 if(retained){assert(!ok&&!port.appExitSafe()&&strstr(runtime.error(),"retention barrier"));assert(h.unloads==h.sequence.size()-1&&m.bus[0]&&m.bus[1]&&m.spi);}
 else {assert(ok&&port.quiescent()&&port.appExitSafe()&&!m.pad_held&&!h.timer&&!h.input);assert(h.entries==((test==RepeatWake||test==LightRefusal)?2u:1u));}
 fprintf(stderr,"Hybrid real Runtime target=%s case=%u PASS entries=%u restores=%u unloads=%u retained=%u\n",targets[target],test,h.entries,h.restores,h.unloads,retained);
 _exit(0);
}
}
extern "C" void watch_test_unloading(){++h.unloads;}
extern "C" void watch_test_loading(const char*path){const char*name=strrchr(path,'/');name=name?name+1:path;
 if(!strcmp(name,"driver.elf")){h.drivers++;return;}
 m.previous_app=m.app;m.app=name;m.app_start=m.time;m.frames_in_app=0;m.clock_ready=false;m.keys_in_app=0;
 if(m.app=="springboard.elf")memcpy(m.retained_clock,m.frame,sizeof(m.frame));
 h.sequence.emplace_back(name);fprintf(stderr,"Hybrid load %s at %llu ms\n",name,(unsigned long long)m.time);
}
int main(int argc,char**argv){assert(argc==2);
 for(unsigned target=0;target<6;target++)for(unsigned test=0;test<=CrownDuringDiagnostic;test++){
  if(!target&&(test==RepeatWake||test==LightRefusal))continue;
  pid_t p=fork();assert(p>=0);if(!p)runHybrid(argv[1],target,(Case)test);
  int result;assert(waitpid(p,&result,0)==p&&WIFEXITED(result)&&WEXITSTATUS(result)==(test==TimerDeep?77:0));
 }
 puts("Hybrid: real Runtime/seven drivers, all apps, state/precision, timer/crown boundaries, retained cleanup, retries and terminal Deep PASS");
}
