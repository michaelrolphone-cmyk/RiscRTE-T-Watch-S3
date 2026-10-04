/* Real Wi-Fi driver against bounded raw radio capability, no network I/O. */
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "../drivers/twatch_wifi/driver.c"
static unsigned joins, leaves, releases, cancellations, stops, starts, polls;
static bool fail_claim, fail_leave, fail_release, fail_cancel, fail_stop, fail_scan;
static bool owned; static uint64_t generation;
static garden_radio_scan_result_v1 snapshot;
static bool raw_claim(void*c,uint64_t*t){(void)c;assert(!owned);*t=0;if(fail_claim)return false;owned=true;*t=++generation;return true;}
static bool raw_join(void*c,uint64_t t,const char*s,const char*p){(void)c;assert(owned&&t==generation&&s&&p);joins++;return true;}
static bool raw_state(void*c,uint64_t t,uint8_t*s,int8_t*r){(void)c;assert(owned&&t==generation);*s=2;*r=-42;return true;}
static bool raw_leave(void*c,uint64_t t){(void)c;assert(owned&&t==generation);leaves++;return !fail_leave;}
static bool raw_release(void*c,uint64_t t){(void)c;assert(owned&&t==generation);releases++;if(fail_release)return false;owned=false;return true;}
static bool raw_ap(void*c,uint64_t t,const char*s,const char*p,const uint8_t*a,const uint8_t*g,const uint8_t*m){(void)c;(void)t;(void)s;(void)p;(void)a;(void)g;(void)m;return false;}
static bool raw_stop(void*c,uint64_t t){(void)c;assert(owned&&t==generation);stops++;return !fail_stop;}
static bool raw_addresses(void*c,uint64_t t,uint8_t*s,uint8_t*a){(void)c;assert(owned&&t==generation);memset(s,0,12);memset(a,0,12);return true;}
static bool raw_scan(void*c,uint64_t t){(void)c;assert(owned&&t==generation);starts++;return !fail_scan;}
static bool raw_poll(void*c,uint64_t t,garden_radio_scan_result_v1*r){(void)c;assert(owned&&t==generation&&r->struct_size==sizeof(*r));polls++;if(fail_scan)return false;*r=snapshot;return true;}
static bool raw_cancel(void*c,uint64_t t){(void)c;assert(owned&&t==generation);cancellations++;return !fail_cancel;}
static garden_radio_v1 raw={.api_version=1,.struct_size=sizeof(raw),.claim=raw_claim,.join=raw_join,.state=raw_state,.leave=raw_leave,.release=raw_release,.start_ap=raw_ap,.stop_ap=raw_stop,.addresses=raw_addresses,.scan_start=raw_scan,.scan_poll=raw_poll,.scan_cancel=raw_cancel};
static risc_hw_radio_v1 config={sizeof(config),0,3};
static risc_hardware_device_v1 device={1,sizeof(device),15,"espressif,esp32s3-wifi","unspecified","radio.integrated",1,sizeof(config),&config};
static risc_provider_dependency_v1 deps[]={{"hardware.device",1,&device},{"platform.radio",1,&raw}};
int main(void){
 const risc_driver_v2*d=t5_driver_get(2);assert(d&&!t5_driver_get(1));
 const wifi_api_v1*a=d->capability;assert(a->struct_size>=WIFI_MANAGEMENT_V1_SIZE);
 assert(d->start(deps,2)&&owned&&!d->start(deps,2));
 char ssid[34],password[65];memset(ssid,'S',sizeof(ssid));memset(password,'p',sizeof(password));
 assert(!a->connect(0,ssid,"password")&&!a->connect(0,"SSID",password));
 ssid[32]=0;password[63]=0;assert(a->connect(0,ssid,password)&&joins==1);
 assert(a->status(0)==WIFI_LINK_UP&&a->rssi(0)==-42);
 assert(a->scan_start(0)&&starts==1);
 snapshot=(garden_radio_scan_result_v1){.struct_size=sizeof(snapshot),.count=16,.state=GARDEN_RADIO_SCAN_DONE};
 for(unsigned i=0;i<16;i++){memset(snapshot.entries[i].ssid,'a',32);snapshot.entries[i].ssid[32]=0;snapshot.entries[i].channel=1;snapshot.entries[i].rssi=-42;}
 struct{uint32_t before;garden_radio_scan_result_v1 value;uint32_t after;} guarded={0x1234,{.struct_size=sizeof(snapshot)},0x5678};
 assert(a->scan_poll(0,&guarded.value)&&guarded.value.count==16&&guarded.before==0x1234&&guarded.after==0x5678);
 garden_radio_scan_result_v1 previous=guarded.value;
 for(unsigned bad=0;bad<6;bad++){
  garden_radio_scan_result_v1 valid=snapshot;
  if(bad==0)snapshot.count=17;if(bad==1)snapshot.state=4;if(bad==2)snapshot.reserved=1;
  if(bad==3)snapshot.entries[15].ssid[32]='x';if(bad==4)snapshot.entries[15].reserved=1;if(bad==5)snapshot.entries[15].channel=15;
  assert(!a->scan_poll(0,&guarded.value)&&!memcmp(&guarded.value,&previous,sizeof(previous)));
  snapshot=valid;
 }
 guarded.value.struct_size=0;unsigned old=polls;assert(!a->scan_poll(0,&guarded.value)&&polls==old);guarded.value=previous;
 fail_scan=true;assert(!a->scan_poll(0,&guarded.value)&&!a->scan_start(0));fail_scan=false;
 fail_cancel=true;old=leaves;assert(!a->disconnect_checked(0)&&leaves==old+1&&owned);fail_cancel=false;
 fail_leave=true;assert(!a->disconnect_checked(0)&&owned);fail_leave=false;assert(a->disconnect_checked(0));
 fail_cancel=fail_stop=fail_leave=true;old=leaves;unsigned oldStops=stops,oldReleases=releases;
 assert(!d->quiesce()&&owned&&leaves==old+1&&stops==oldStops+1&&releases==oldReleases);
 assert(!a->connect(0,"SSID","password")&&!a->scan_start(0));
 fail_cancel=fail_stop=fail_leave=false;fail_release=true;assert(!d->quiesce()&&owned);fail_release=false;
 assert(d->quiesce()&&!owned);d->stop();assert(d->quiesce());
 /* A v1 prefix-only provider is still usable; optional scan never dereferences
  * missing fields. A wrong/truncated prefix rejects before native claim. */
 raw.struct_size=GARDEN_RADIO_PREFIX_V1_SIZE;assert(d->start(deps,2));old=starts;
 assert(!a->scan_start(0)&&starts==old&&a->connect(0,"SSID","password")&&a->disconnect_checked(0));assert(d->quiesce());
 raw.struct_size=GARDEN_RADIO_PREFIX_V1_SIZE-1;assert(!d->start(deps,2)&&!owned);
 raw.struct_size=sizeof(raw);raw.api_version=2;assert(!d->start(deps,2));raw.api_version=1;
 fail_claim=true;assert(!d->start(deps,2)&&!owned&&d->quiesce());fail_claim=false;
 assert(d->start(deps,2));assert(d->quiesce());
 puts("Wi-Fi production driver: legacy ABI, scans, bounds, cleanup/retry passed");
}
