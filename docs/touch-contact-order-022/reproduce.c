#include "PortableTouch.h"
#include <assert.h>
#include <stdio.h>
static risc_touch_snapshot_v1 physical;
static uint64_t when;
void hid_renderer_watch_report(risc_touch_snapshot_v1 *s){*s=physical;}
uint64_t hid_renderer_watch_millis(void){return when;}
const risc_touch_api_v1 *hid_watch_touch_start(void);
void hid_watch_touch_stop(void);
int main(void){
 const risc_touch_api_v1 *api=hid_watch_touch_start();
 portable_touch touch={.api=api,.subscription=api->subscribe(api->context)};
 portable_touch_sample sample;
 assert(touch.subscription&&!portable_touch_next(&touch,&sample));
 when=10;physical.contact_count=1;physical.contacts[0]=(risc_touch_contact_v1){.id=1,.x=20,.y=100};
 assert(portable_touch_collect(&touch)&&portable_touch_next(&touch,&sample)&&sample.began);
 when=20;physical.contact_count=2;physical.contacts[0].x=140;physical.contacts[1]=(risc_touch_contact_v1){.id=2,.x=170,.y=120};
 assert(portable_touch_collect(&touch));
 when=21;
 assert(portable_touch_next(&touch,&sample));
 risc_touch_snapshot_v1 latest={0};assert(api->snapshot(api->context,&latest));
 fprintf(stderr,"Watch .2.1 dispatch sequence=%llu event_ms=%llu contacts=%u snapshot_sequence=%llu snapshot_ms=%llu down=%u moved=%u cancelled=%u x=%u\n",(unsigned long long)touch.sequence,(unsigned long long)touch.timestamp_ms,latest.contact_count,(unsigned long long)latest.sequence,(unsigned long long)latest.timestamp_ms,sample.down,sample.moved,sample.cancelled,sample.x);
 assert(sample.cancelled&&!sample.down);
 assert(api->unsubscribe(api->context,touch.subscription));hid_watch_touch_stop();
 return 0;
}
