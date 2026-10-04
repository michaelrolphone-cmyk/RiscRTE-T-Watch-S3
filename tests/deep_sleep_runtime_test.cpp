// Same production Runtime, driver ELFs, Clock and raw CPU broker as the GUI
// integration. This additionally drives the real deep path, not app-only mocks.
#define main watch_gui_test_main
#include "launcher_runtime_test.cpp"
#undef main
#include <sys/wait.h>
#include <unistd.h>
namespace {
bool deepValid(uint8_t pin){assert(pin==21);return true;}
bool deepReady(){assert(!m.held&&!m.levels[45]&&m.pad_held);return true;}
bool deepArm(uint8_t pin,bool high,bool pullup){assert(pin==21&&!high&&pullup);++m.sleep_attempts;m.sleep_attempt_at=m.time;return m.sleep_fault==0||m.sleep_fault==2;}
bool deepClear(uint8_t pin,bool pullup){assert(pin==21&&pullup);return m.sleep_fault!=4;}
void deepEnter(){
 assert(m.sleep_attempts==1&&m.pad_held&&!m.levels[45]&&m.frame_rows==240&&m.clockReady==1&&!m.sleep_unloads);
 assert(m.registers[0][0x40]==0&&m.registers[0][0x41]==8&&m.registers[0][0x42]==0&&!m.dateWrites);
 for(unsigned i=0;i<sizeof(m.frame);++i)assert(!m.frame[i]);
 if(!m.sleep_fault)_exit(77);
 assert(m.sleep_fault==2); // Illegal returning backend must retain everything.
}
bool deepHold(uint8_t pin,bool enable){
 assert(pin==45&&!m.levels[45]);
 if(enable){m.pad_held=true;if(m.sleep_fault==5){++m.sleep_attempts;m.sleep_attempt_at=m.time;return false;}return true;}
 if(m.sleep_fault==3||m.sleep_fault==5)return false;
 m.pad_held=false;return true;
}
int one(const char*root,unsigned fault){
 m=Model{};m.sleep_test=true;m.sleep_fault=fault;m.registers[0][3]=0x4a;m.registers[0][0x49]=8;
 m.registers[0][0x34]=0x0f;m.registers[0][0x35]=0xa0;
 const uint8_t raw[]={0,0x40,0,4,0,0x10,0x26};memcpy(m.registers[1]+2,raw,7);
 RiscCpu::Hardware hardware={owner,now,delay,gpioOpen,gpioWrite,gpioRead,gpioPwm,gpioClose,i2cOpen,i2cTransfer,i2cClose,spiOpen,spiBegin,spiTransfer,spiEnd,spiClose};
 hardware.deepWakeValid=deepValid;hardware.deepReady=deepReady;hardware.deepWakeArm=deepArm;hardware.deepWakeClear=deepClear;hardware.deepSleep=deepEnter;hardware.deepHold=deepHold;
 RiscCpu::Port port(hardware);cpu=&port;
 RiscBoot::Runtime runtime({owner,live,delay,[](const char*s){puts(s);if(strstr(s,"error="))return true;return log(s);},bind,&kv,[](){return cpu->appExitSafe();}});
 assert(runtime.prepare(root));bool ok=runtime.run();
 assert(m.clockReady==1&&m.sleep_attempts==1&&!m.dateWrites&&!memcmp(m.registers[1]+2,raw,7));
 if(fault==1){assert(ok&&port.quiescent()&&port.appExitSafe()&&!m.pad_held&&m.sleep_unloads==8);for(bool pin:m.pins)assert(!pin);}
 else {assert(!ok&&strstr(runtime.error(),"retention barrier")&&!port.appExitSafe()&&!m.sleep_unloads&&m.pad_held);assert(m.bus[0]&&m.bus[1]&&m.spi);}
 fprintf(stderr,"Real Watch deep runtime fault=%u PASS, app unloads=%u retained=%u\n",fault,m.sleep_unloads,!ok);_exit(0);
}
}
int main(int argc,char**argv){
 assert(argc==2);
 for(unsigned fault=0;fault<6;++fault){pid_t pid=fork();assert(pid>=0);if(!pid)_exit(one(argv[1],fault));int status;assert(waitpid(pid,&status,0)==pid&&WIFEXITED(status)&&WEXITSTATUS(status)==(fault?0:77));}
 // Two more independent boots prove no process/app/claim state continues.
 for(unsigned n=0;n<2;++n){pid_t pid=fork();assert(pid>=0);if(!pid)_exit(one(argv[1],0));int status;assert(waitpid(pid,&status,0)==pid&&WIFEXITED(status)&&WEXITSTATUS(status)==77);}
 puts("Real Runtime/Clock/seven drivers: deep terminal boots, ordinary refusal and four retained faults passed");return 0;
}
