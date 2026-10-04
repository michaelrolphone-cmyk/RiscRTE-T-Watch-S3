#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "RiscKeyValueV1.h"
#define WATCH_FACE_COUNT 8u
#define WATCH_FACE_KEY "watch_face"
#define WATCH_FACE_STORE_INSTANCE 1u
#define WATCH_FACE_HOLD_MS 600u
#define WATCH_FACE_PITCH (108*256)
typedef struct {
    bool open,neutral,down,hold,moved,consume,pulse_active;
    uint8_t contact,selected,target,pulse_face;
    uint16_t x,y,last_x,last_y;
    uint32_t began,last_move,last_tick,phase,pulse_started;
    int position,velocity,travel;
    bool snapping;
} watch_face_picker;
enum { WATCH_FACE_NONE, WATCH_FACE_LAUNCHER, WATCH_FACE_OPEN, WATCH_FACE_SELECT };
static inline unsigned watch_face_nearest(const watch_face_picker*p) {
    int n=(-p->position+WATCH_FACE_PITCH/2)/WATCH_FACE_PITCH;
    return n<0?0:n>=8?7:(unsigned)n;
}
static inline void watch_face_reset_contact(watch_face_picker*p) {
    p->neutral=false;p->down=false;p->hold=false;p->consume=true;p->velocity=0;
}
static inline void watch_face_close(watch_face_picker*p) {
    p->open=false;watch_face_reset_contact(p);
}
static inline unsigned watch_face_input(watch_face_picker*p,uint32_t now,bool valid,unsigned count,unsigned id,unsigned x,unsigned y) {
    if(!valid||count>1||(count&&(x>=240||y>=240))){watch_face_reset_contact(p);return WATCH_FACE_NONE;}
    if(!count) {
        unsigned result=WATCH_FACE_NONE;
        if(p->down&&p->open&&!p->consume&&!p->moved) {
            int best=-1,distance=1000000;
            for(unsigned i=0;i<8;i++) {
                int offset=(int)i*WATCH_FACE_PITCH+p->position,abs=offset<0?-offset:offset;
                int scale=256-(abs<135*256?abs:135*256)*102/(108*256),half=66*scale/256;
                int dx=(int)p->last_x-(120+offset/256),dy=(int)p->last_y-92;
                if(dx>-half&&dx<half&&dy>-half&&dy<half&&abs<distance){best=(int)i;distance=abs;}
            }
            if(best>=0){p->target=(uint8_t)best;p->snapping=true;if(distance<20*256){result=WATCH_FACE_SELECT;p->pulse_face=(uint8_t)best;p->pulse_started=now;p->pulse_active=true;}}
        }
        if(p->down&&(uint32_t)(now-p->last_move)>90)p->velocity=0;
        p->neutral=true;p->down=false;p->consume=false;p->hold=false;return result;
    }
    if(!p->neutral||p->consume)return WATCH_FACE_NONE;
    if(!p->down) {
        p->down=true;p->contact=(uint8_t)id;p->x=p->last_x=(uint16_t)x;p->y=p->last_y=(uint16_t)y;
        p->began=p->last_move=now;p->hold=true;p->moved=false;p->travel=0;p->velocity=0;p->snapping=false;return WATCH_FACE_NONE;
    }
    if(id!=p->contact){watch_face_reset_contact(p);return WATCH_FACE_NONE;}
    int dx=(int)x-p->x,dy=(int)y-p->y,mx=(int)x-p->last_x;
    if(dx>8||dx<-8||dy>8||dy<-8)p->hold=false;
    if(p->open) {
        p->travel+=mx<0?-mx:mx;if(p->travel>=6||dy>=6||dy<=-6)p->moved=true;
        if(mx) {
            int d=mx*256,low=-7*WATCH_FACE_PITCH;
            int overshoot=p->position<low?low-p->position:p->position>0?p->position:0;
            if((p->position>0&&d>0)||(p->position<low&&d<0))d=(int)((int64_t)d*24*256/(24*256+overshoot));
            p->position+=d;
            /* Source pointer velocity: .6*delta + .4*previous, in px/frame. */
            p->velocity=(p->velocity*2+mx*256*3)/5;p->last_move=now;
        }
    } else if(dx>=20||dx<=-20||dy>=20||dy<=-20) {
        watch_face_reset_contact(p);return WATCH_FACE_LAUNCHER;
    } else if(p->hold&&(uint32_t)(now-p->began)>=WATCH_FACE_HOLD_MS) {
        p->open=true;p->position=-(int)p->selected*WATCH_FACE_PITCH;p->target=p->selected;p->snapping=true;
        watch_face_reset_contact(p);p->last_tick=now;return WATCH_FACE_OPEN;
    }
    p->last_x=(uint16_t)x;p->last_y=(uint16_t)y;return WATCH_FACE_NONE;
}
/* The supplied source spring at its nominal 60Hz: progressive edge friction,
 * -0.09 displacement acceleration, .8 damping outside, .82..94 damping inside,
 * and .84 snap easing. A fixed simulation tick makes 8/20/50/95ms rendering
 * intervals produce the same motion, instead of applying friction per frame.
 * At most six ticks are recovered after a stall; no unbounded catch-up loop. */
static inline void watch_face_animate(watch_face_picker*p,uint32_t now) {
    uint32_t dt=now-p->last_tick;p->last_tick=now;
    if(p->pulse_active&&(uint32_t)(now-p->pulse_started)>=334u)p->pulse_active=false;
    if(!p->open||p->down){p->phase=0;return;}
    if(dt>100)dt=100;
    p->phase+=dt*3u;
    while(p->phase>=50u) {
        p->phase-=50u;
        int low=-7*WATCH_FACE_PITCH;
        bool out=p->position<low||p->position>0;
        if(!p->snapping||out) {
            if(out)p->snapping=false;
            int overshoot=p->position<low?p->position-low:p->position>0?p->position:0;
            if(overshoot){p->velocity-=overshoot*9/100;p->velocity=p->velocity*4/5;}
            else {
                int distance=p->position-low<-p->position?p->position-low:-p->position;
                if(distance>50*256)distance=50*256;
                /* .94-.12*(1-distance/50) in exact Q16. */
                int damping=53740+distance*7864/(50*256);
                p->velocity=(int)((int64_t)p->velocity*damping/65536);
            }
            p->position+=p->velocity;
            if(!p->snapping&&p->position>=low&&p->position<=0&&p->velocity>-103&&p->velocity<103){p->target=(uint8_t)watch_face_nearest(p);p->snapping=true;}
        }
        if(p->snapping){int d=-(int)p->target*WATCH_FACE_PITCH-p->position;p->position+=d*16/100;if(d>-7&&d<7)p->position=-(int)p->target*WATCH_FACE_PITCH;}
    }
}
static inline bool watch_face_store_valid(const risc_key_value_v1*k) {
    return k&&k->api_version==1&&k->struct_size>=sizeof(*k)&&k->get&&k->put;
}
static inline int watch_face_load(const risc_key_value_v1*k,unsigned*out) {
    *out=0;if(!watch_face_store_valid(k))return RISC_KEY_VALUE_CONTEXT;
    uint8_t b[4];uint32_t size=0;int rc=k->get(k->context,WATCH_FACE_KEY,b,sizeof(b),&size);
    if(rc!=RISC_KEY_VALUE_OK)return rc;
    if(size!=4||b[0]!=0x46||b[1]!=1||b[2]>=8||b[3]!=(uint8_t)(b[2]^0xa5u))return RISC_KEY_VALUE_INVALID;
    *out=b[2];return RISC_KEY_VALUE_OK;
}
static inline bool watch_face_save(const risc_key_value_v1*k,unsigned face) {
    if(face>=8||!watch_face_store_valid(k))return false;
    unsigned previous;if(watch_face_load(k,&previous)==RISC_KEY_VALUE_OK&&previous==face)return true;
    uint8_t b[]={0x46,1,(uint8_t)face,(uint8_t)(face^0xa5u)};
    if(k->put(k->context,WATCH_FACE_KEY,b,sizeof(b))!=RISC_KEY_VALUE_OK)return false;
    return watch_face_load(k,&previous)==RISC_KEY_VALUE_OK&&previous==face;
}
