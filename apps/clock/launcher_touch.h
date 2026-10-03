#pragma once
#include "RiscTouchV1.h"
/* Watch deployment policy, not a raw-provider ABI change. The panel is rotated
 * 180 degrees; map copied snapshot coordinates before interpreting gestures. */
typedef struct {
    risc_runtime_capability_v1 grant;
    const risc_touch_api_v1 *api;
    uint64_t subscription;
    bool neutral, down;
    uint8_t id;
    uint16_t x, y;
} watch_launcher_touch;
static bool launcher_touch_close(watch_launcher_touch *t) {
    if (t->subscription && !t->api->unsubscribe(t->api->context,t->subscription)) return false;
    t->subscription=0;
    if (t->grant.api && !rt->release(&t->grant)) return false;
    *t=(watch_launcher_touch){0}; return true;
}
static bool launcher_touch_open(watch_launcher_touch *t) {
    *t=(watch_launcher_touch){.grant={.struct_size=sizeof(t->grant)}};
    if (!rt->acquire("input.touch.raw",1,0,&t->grant)) return false;
    t->api=t->grant.api;
    if (!t->api || t->api->api_version!=1 || t->api->struct_size<sizeof(*t->api) ||
        !t->api->subscribe || !t->api->unsubscribe || !t->api->poll || !t->api->next || !t->api->snapshot) return false;
    t->subscription=t->api->subscribe(t->api->context);
    risc_touch_snapshot_v1 s={0};
    if (!t->subscription || !t->api->snapshot(t->api->context,&s)) return false;
    t->neutral=s.contact_count==0; return true;
}
static bool launcher_touch_swipe(watch_launcher_touch *t,bool *activity) {
    *activity=false;
    if (!t->subscription) return false;
    bool ok=t->api->poll(t->api->context,1);
    for(unsigned n=0;n<RISC_TOUCH_QUEUE_LENGTH;n++) {
        risc_touch_event_v1 e={0};
        int32_t count=t->api->next(t->api->context,t->subscription,&e);
        if(count<=0){if(count<0)ok=false;break;}
        *activity=true;
    }
    risc_touch_snapshot_v1 s={0};
    if (!t->api->snapshot(t->api->context,&s) || !ok || s.width!=240 || s.height!=240 || s.contact_count>1) {
        t->neutral=t->down=false; return false;
    }
    if (!s.contact_count) {t->neutral=true;t->down=false;return false;}
    *activity=true;
    if (!t->neutral) return false;
    if(s.contacts[0].x>=s.width || s.contacts[0].y>=s.height){t->neutral=t->down=false;return false;}
    uint16_t x=(uint16_t)(s.width-1u-s.contacts[0].x),y=(uint16_t)(s.height-1u-s.contacts[0].y);
    if(!t->down){t->down=true;t->id=s.contacts[0].id;t->x=x;t->y=y;return false;}
    if(t->id!=s.contacts[0].id){t->neutral=t->down=false;return false;}
    int dx=(int)x-t->x,dy=(int)y-t->y;
    if(dx>=20 || dx<=-20 || dy>=20 || dy<=-20){t->neutral=t->down=false;return true;}
    return false;
}
