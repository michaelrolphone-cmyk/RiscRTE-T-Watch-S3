/* Explicitly controlled persistent BLE transport. No host stack, discovery,
 * advertising or pairing is started implicitly. Failed cleanup retains token. */
#include "twatch_support.h"
#include "RiscBluetoothHciV1.h"
#include "RiscHciControllerStatusV1.h"
#include "twatch_bluetooth.h"
static const twatch_hci_controller_v1 *hw;
static const risc_hci_controller_status_v1 *control;
static uint64_t session;
static bool started;
static bool state(void*c,uint8_t*out) {
 (void)c;if(!out)return false;*out=PORTABLE_BLUETOOTH_RETAINED;
 return started && control && control->status && control->status(hw->context,session,out) && *out<=PORTABLE_BLUETOOTH_RETAINED;
}
static bool enabled(void*c,bool on) {
 (void)c;if(!started)return false;
 uint8_t current=PORTABLE_BLUETOOTH_RETAINED;
 if(!state(NULL,&current))return false;
 if(on) {
  if(current==PORTABLE_BLUETOOTH_ON)return true;
  if(current!=PORTABLE_BLUETOOTH_OFF || session)return false;
  if(!hw->open(hw->context,0,&session) || !session)return false;
  return state(NULL,&current) && current==PORTABLE_BLUETOOTH_ON;
 }
 if(session && !hw->close(hw->context,session))return false;
 session=0;
 return state(NULL,&current) && current==PORTABLE_BLUETOOTH_OFF;
}
static bool send_packet(void*c,uint8_t type,const uint8_t*p,size_t n) {
 (void)c;uint8_t current;
 if(!p || !session || !state(NULL,&current) || current!=PORTABLE_BLUETOOTH_ON)return false;
 if(type==1){if(n<3||n>258||n!=(size_t)p[2]+3)return false;}
 else if(type==2){if(n<4||n>1028||n!=4u+p[2]+((size_t)p[3]<<8))return false;}
 else return false;
 return hw->send(hw->context,session,type,p,n,20);
}
static int32_t next_packet(void*c,uint8_t*type,uint8_t*p,size_t cap,size_t*length) {
 (void)c;if(length)*length=0;uint8_t current;
 if(!type||!p||!length||cap<1028||!session||!state(NULL,&current)||current!=PORTABLE_BLUETOOTH_ON)return -1;
 if(!hw->receive(hw->context,session,type,p,1028,length,0))return -1;
 if(!*length)return 0;
 size_t n=*length;
 return ((*type==4&&n>=2&&n<=257&&n==2u+p[1]) || (*type==2&&n>=4&&n<=1028&&n==4u+p[2]+((size_t)p[3]<<8)))?1:(*length=0,-1);
}
static bool quiesce(void) {
 if(started && !enabled(NULL,false))return false;
 started=false;hw=NULL;control=NULL;return true;
}
static bool start(const risc_provider_dependency_v1*d,size_t n) {
 if(started||session)return false;
 const risc_hw_radio_v1 *config=tw_config(d,n,"espressif,esp32s3-ble","radio.integrated",sizeof(*config));
 if(!config||config->unit||config->features!=1)return false;
 control=tw_dep(d,n,"platform.hci.controller",sizeof(*control));hw=control?&control->transport:NULL;
 if(!hw||!hw->open||!hw->send||!hw->receive||!hw->close||!control->status){hw=NULL;control=NULL;return false;}
 uint8_t initial=PORTABLE_BLUETOOTH_RETAINED;
 if(!control->status(hw->context,0,&initial)||initial!=PORTABLE_BLUETOOTH_OFF){hw=NULL;control=NULL;return false;}
 started=true;return true; /* Enabling is an explicit application preference. */
}
_Static_assert(offsetof(portable_bluetooth_control_v1,set_enabled)==sizeof(risc_bluetooth_hci_v1),"Unchanged Bluetooth packet prefix");
static const portable_bluetooth_control_v1 api={1,sizeof(api),NULL,send_packet,next_packet,enabled,state};
TW_DRIVER("twatch-ble","bluetooth.hci",1,api)
