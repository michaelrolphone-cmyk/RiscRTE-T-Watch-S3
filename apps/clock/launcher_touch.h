#pragma once
#include "RiscTouchV1.h"
/* Watch deployment policy, not a raw-provider ABI change. The confirmed
 * touch-direction variant uses identity coordinates in every GUI client. */
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
/* Drain queued notifications, then use the provider's authoritative snapshot.
 * A gap/multitouch/id replacement cancels every gesture until neutral. */
typedef struct {
    uint32_t now;
    uint16_t x,y;
    uint8_t count,id;
    bool valid,activity;
} watch_launcher_observation;
/* Capture does not mutate either gesture recognizer. The renderer may collect
 * these observations, then replay them in order after all frame writes stop. */
static watch_launcher_observation launcher_touch_capture(watch_launcher_touch *t,uint32_t now) {
    watch_launcher_observation o={.now=now};
    if(!t->subscription)return o;
    bool ok=t->api->poll(t->api->context,1);
    for(unsigned n=0;n<RISC_TOUCH_QUEUE_LENGTH;n++) {
        risc_touch_event_v1 e={0};int32_t count=t->api->next(t->api->context,t->subscription,&e);
        if(count<=0){if(count<0)ok=false;break;}o.activity=true;
    }
    risc_touch_snapshot_v1 s={0};
    o.valid=t->api->snapshot(t->api->context,&s)&&ok&&s.width==240&&s.height==240;
    o.count=s.contact_count;o.id=s.contacts[0].id;o.x=s.contacts[0].x;o.y=s.contacts[0].y;
    if(o.count)o.activity=true;
    return o;
}
static unsigned launcher_touch_observe(watch_face_picker *picker,const watch_launcher_observation *o) {
    uint32_t now=o->now;bool valid=o->valid;
#ifdef WATCH_QUICK_ACTIONS
    bool consumed=pqa_input(&clock_quick.ui,now,valid,o->count,o->id,o->x,o->y,!picker->open);
    if(consumed){watch_face_reset_contact(picker);return WATCH_FACE_NONE;}
    if(clock_quick.ui.route==PQA_REPLAY) {
        (void)watch_face_input(picker,clock_quick.ui.start_ms,true,0,0,0,0);
        (void)watch_face_input(picker,clock_quick.ui.start_ms,true,1,clock_quick.ui.start_id,(unsigned)clock_quick.ui.start_x,(unsigned)clock_quick.ui.start_y);
    }
#endif
    return watch_face_input(picker,now,valid,o->count,o->id,o->x,o->y);
}
static unsigned launcher_touch_sample(watch_launcher_touch *t,watch_face_picker *picker,uint32_t now,bool *activity) {
    *activity=false;if(!t->subscription)return WATCH_FACE_NONE;
    watch_launcher_observation o=launcher_touch_capture(t,now);
    *activity=o.activity;
    return launcher_touch_observe(picker,&o);
}
