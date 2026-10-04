#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "RiscKeyValueV1.h"
#include "catalog.h"
#define WATCH_FACE_KEY "watch_face"
#define WATCH_FACE_STORE_INSTANCE 1u
#define WATCH_FACE_HOLD_MS 600u
#define WATCH_FACE_PITCH (108*256)
#define WATCH_CATEGORY_PITCH (240*256)
#define WATCH_CATEGORY_PERIOD (WATCH_FACE_CATEGORY_COUNT*WATCH_CATEGORY_PITCH)
typedef struct {
    bool open,neutral,down,hold,moved,consume,pulse_active,tap_blocked;
    uint8_t contact,selected,target,pulse_face,category,axis;
    uint16_t x,y,last_x,last_y;
    uint32_t began,last_move,last_tick,phase,pulse_started;
    int position,velocity,travel;
    int category_position,category_velocity,category_positions[WATCH_FACE_CATEGORY_COUNT];
    uint8_t category_target;
    bool snapping,category_snapping;
} watch_face_picker;
enum { WATCH_FACE_NONE, WATCH_FACE_LAUNCHER, WATCH_FACE_OPEN, WATCH_FACE_SELECT };
static inline unsigned watch_axis_nearest(int position,int pitch,unsigned count) {
    int n=(-position+pitch/2)/pitch;
    return n<0?0:n>=(int)count?count-1:(unsigned)n;
}
static inline unsigned watch_face_nearest(const watch_face_picker*p) {
    return watch_axis_nearest(p->position,WATCH_FACE_PITCH,watch_face_page_for(p->category)->count);
}
static inline void watch_category_normalize(watch_face_picker*p) {
    p->category_position%=(int)WATCH_CATEGORY_PERIOD;
    if(p->category_position>0)p->category_position-=(int)WATCH_CATEGORY_PERIOD;
}
static inline unsigned watch_category_nearest(const watch_face_picker*p) {
    return (unsigned)((-p->category_position+WATCH_CATEGORY_PITCH/2)/WATCH_CATEGORY_PITCH)%WATCH_FACE_CATEGORY_COUNT;
}
static inline bool watch_category_settled(const watch_face_picker*p) {
    return p->category_position==-(int)p->category*WATCH_CATEGORY_PITCH&&p->category_velocity==0;
}
static inline void watch_category_sync(watch_face_picker*p) {
    watch_category_normalize(p);
    unsigned next=watch_category_nearest(p);
    p->category_positions[p->category]=p->position;
    if(next!=p->category) {
        p->category=(uint8_t)next;p->position=p->category_positions[next];
        p->target=(uint8_t)watch_face_nearest(p);p->velocity=0;p->snapping=true;p->pulse_active=false;
    }
}
static inline void watch_face_reset_contact(watch_face_picker*p) {
    p->neutral=false;p->down=false;p->hold=false;p->consume=true;p->velocity=0;p->axis=0;
    p->category_velocity=0;p->category_target=(uint8_t)watch_category_nearest(p);p->category_snapping=true;
}
static inline void watch_face_close(watch_face_picker*p) {
    p->open=false;watch_face_reset_contact(p);
}
static inline unsigned watch_face_input(watch_face_picker*p,uint32_t now,bool valid,unsigned count,unsigned id,unsigned x,unsigned y) {
    if(!valid||count>1||(count&&(x>=240||y>=240))){watch_face_reset_contact(p);return WATCH_FACE_NONE;}
    if(!count) {
        unsigned result=WATCH_FACE_NONE;
        if(p->down&&p->open&&!p->consume&&!p->moved&&!p->axis&&!p->tap_blocked&&watch_category_settled(p)) {
            int best=-1,distance=1000000;
            for(unsigned i=0;i<watch_face_page_for(p->category)->count;i++) {
                int offset=(int)i*WATCH_FACE_PITCH+p->position,abs=offset<0?-offset:offset;
                int scale=256-(abs<135*256?abs:135*256)*102/(108*256),half=66*scale/256;
                int dx=(int)p->last_x-(120+offset/256),dy=(int)p->last_y-92;
                if(dx>-half&&dx<half&&dy>-half&&dy<half&&abs<distance){best=(int)i;distance=abs;}
            }
            if(best>=0){p->target=(uint8_t)best;p->snapping=true;if(distance<20*256){result=WATCH_FACE_SELECT;p->pulse_face=watch_face_page_for(p->category)->ids[best];p->pulse_started=now;p->pulse_active=true;}}
        }
        if(p->down&&(uint32_t)(now-p->last_move)>90){p->velocity=0;p->category_velocity=0;}
        p->neutral=true;p->down=false;p->consume=false;p->hold=false;return result;
    }
    if(!p->neutral||p->consume)return WATCH_FACE_NONE;
    if(!p->down) {
        p->down=true;p->contact=(uint8_t)id;p->x=p->last_x=(uint16_t)x;p->y=p->last_y=(uint16_t)y;
        p->began=p->last_move=now;p->hold=true;p->moved=false;p->travel=0;p->velocity=0;p->axis=0;p->snapping=false;
        p->tap_blocked=!watch_category_settled(p);p->category_velocity=0;p->category_snapping=false;return WATCH_FACE_NONE;
    }
    if(id!=p->contact){watch_face_reset_contact(p);return WATCH_FACE_NONE;}
    int dx=(int)x-p->x,dy=(int)y-p->y,mx=(int)x-p->last_x,my=(int)y-p->last_y;
    if(dx>8||dx<-8||dy>8||dy<-8)p->hold=false;
    if(p->open) {
        p->travel+=mx<0?-mx:mx;if(p->travel>=6||dy>=6||dy<=-6)p->moved=true;
        /* Lock one axis for the entire contact. A diagonal cannot change
         * category and scroll/select a card in the same gesture. */
        int ax=dx<0?-dx:dx,ay=dy<0?-dy:dy;
        if(!p->axis&&(ax>=8||ay>=8)) {
            if(ax*4>ay*5)p->axis=1;
            else if(ay*4>ax*5)p->axis=2;
            else if(ax>=16||ay>=16)p->axis=ax>=ay?1:2;
            if(p->axis==2)my=dy; /* Include the lock slop in finger translation. */
        }
        if(mx&&p->axis==1&&!p->tap_blocked) {
            int d=mx*256,low=-(int)(watch_face_page_for(p->category)->count-1)*WATCH_FACE_PITCH;
            int overshoot=p->position<low?low-p->position:p->position>0?p->position:0;
            if((p->position>0&&d>0)||(p->position<low&&d<0))d=(int)((int64_t)d*24*256/(24*256+overshoot));
            p->position+=d;
            /* Source pointer velocity: .6*delta + .4*previous, in px/frame. */
            p->velocity=(p->velocity*2+mx*256*3)/5;p->last_move=now;
        }
        if(my&&p->axis==2) {
            p->category_position+=my*256;
            /* Normalize pointer velocity to the same nominal 60Hz unit as the
             * spring, so slow/fast input sampling does not change a fling. */
            uint32_t dt=now-p->last_move;if(!dt)dt=1;if(dt>100)dt=100;
            int speed=my*256*50/(3*(int)dt);
            if(speed>40*256)speed=40*256;
            if(speed<-40*256)speed=-40*256;
            p->category_velocity=(p->category_velocity*2+speed*3)/5;
            p->last_move=now;p->category_snapping=false;watch_category_sync(p);
        }
    } else if(dx>=20||dx<=-20||dy>=20||dy<=-20) {
        watch_face_reset_contact(p);return WATCH_FACE_LAUNCHER;
    } else if(p->hold&&(uint32_t)(now-p->began)>=WATCH_FACE_HOLD_MS) {
        p->open=true;p->category=(uint8_t)watch_face_category_for(p->selected);p->target=(uint8_t)watch_face_index_for(p->category,p->selected);p->position=-(int)p->target*WATCH_FACE_PITCH;p->snapping=true;
        p->category_position=-(int)p->category*WATCH_CATEGORY_PITCH;p->category_positions[p->category]=p->position;
        watch_face_reset_contact(p);p->last_tick=now;return WATCH_FACE_OPEN;
    }
    p->last_x=(uint16_t)x;p->last_y=(uint16_t)y;return WATCH_FACE_NONE;
}
/* The supplied source spring at its nominal 60Hz: progressive edge friction,
 * -0.09 displacement acceleration, .8 damping outside, .82..94 damping inside,
 * and .84 snap easing. A fixed simulation tick makes 8/20/50/95ms rendering
 * intervals produce the same motion, instead of applying friction per frame.
 * At most six ticks are recovered after a stall; no unbounded catch-up loop. */
static inline void watch_axis_step(int*position,int*velocity,uint8_t*target,bool*snapping,int pitch,unsigned count) {
    int low=-(int)(count-1)*pitch;
    bool out=*position<low||*position>0;
    if(!*snapping||out) {
        if(out)*snapping=false;
        int overshoot=*position<low?*position-low:*position>0?*position:0;
        if(overshoot){*velocity-=overshoot*9/100;*velocity=*velocity*4/5;}
        else {
            int distance=*position-low<-*position?*position-low:-*position;
            if(distance>50*256)distance=50*256;
            int damping=53740+distance*7864/(50*256);
            *velocity=(int)((int64_t)*velocity*damping/65536);
        }
        *position+=*velocity;
        if(!*snapping&&*position>=low&&*position<=0&&*velocity>-103&&*velocity<103){*target=(uint8_t)watch_axis_nearest(*position,pitch,count);*snapping=true;}
    }
    if(*snapping){int d=-(int)*target*pitch-*position;*position+=d*16/100;if(d>-7&&d<7){*position=-(int)*target*pitch;*velocity=0;}}
}
/* Cyclic collections have no edge to resist. Retain the interior .94
 * friction and .84 snap easing of the horizontal model across either seam. */
static inline void watch_category_step(watch_face_picker*p) {
    if(!p->category_snapping) {
        p->category_velocity=(int)((int64_t)p->category_velocity*61604/65536);
        p->category_position+=p->category_velocity;watch_category_normalize(p);
        if(p->category_velocity>-103&&p->category_velocity<103){p->category_target=(uint8_t)watch_category_nearest(p);p->category_snapping=true;}
    }
    if(p->category_snapping) {
        int d=-(int)p->category_target*WATCH_CATEGORY_PITCH-p->category_position;
        if(d>(int)WATCH_CATEGORY_PERIOD/2)d-=(int)WATCH_CATEGORY_PERIOD;
        if(d<-(int)WATCH_CATEGORY_PERIOD/2)d+=(int)WATCH_CATEGORY_PERIOD;
        p->category_position+=d*16/100;
        if(d>-7&&d<7){p->category_position=-(int)p->category_target*WATCH_CATEGORY_PITCH;p->category_velocity=0;}
        watch_category_normalize(p);
    }
}
static inline void watch_face_animate(watch_face_picker*p,uint32_t now) {
    uint32_t dt=now-p->last_tick;p->last_tick=now;
    if(p->pulse_active&&(uint32_t)(now-p->pulse_started)>=334u)p->pulse_active=false;
    if(!p->open||p->down){p->phase=0;return;}
    if(dt>100)dt=100;
    p->phase+=dt*3u;
    while(p->phase>=50u) {
        p->phase-=50u;
        watch_category_step(p);
        watch_category_sync(p);
        if(watch_category_settled(p))watch_axis_step(&p->position,&p->velocity,&p->target,&p->snapping,WATCH_FACE_PITCH,watch_face_page_for(p->category)->count);
        p->category_positions[p->category]=p->position;
    }
}
static inline bool watch_face_store_valid(const risc_key_value_v1*k) {
    return k&&k->api_version==1&&k->struct_size>=sizeof(*k)&&k->get&&k->put;
}
static inline int watch_face_load(const risc_key_value_v1*k,unsigned*out) {
    *out=0;if(!watch_face_store_valid(k))return RISC_KEY_VALUE_CONTEXT;
    uint8_t b[4];uint32_t size=0;int rc=k->get(k->context,WATCH_FACE_KEY,b,sizeof(b),&size);
    if(rc!=RISC_KEY_VALUE_OK)return rc;
    if(size!=4||b[0]!=0x46||b[1]!=1||b[2]>=WATCH_FACE_COUNT||b[3]!=(uint8_t)(b[2]^0xa5u))return RISC_KEY_VALUE_INVALID;
    *out=b[2];return RISC_KEY_VALUE_OK;
}
static inline bool watch_face_save(const risc_key_value_v1*k,unsigned face) {
    if(face>=WATCH_FACE_COUNT||!watch_face_store_valid(k))return false;
    unsigned previous;if(watch_face_load(k,&previous)==RISC_KEY_VALUE_OK&&previous==face)return true;
    uint8_t b[]={0x46,1,(uint8_t)face,(uint8_t)(face^0xa5u)};
    if(k->put(k->context,WATCH_FACE_KEY,b,sizeof(b))!=RISC_KEY_VALUE_OK)return false;
    return watch_face_load(k,&previous)==RISC_KEY_VALUE_OK&&previous==face;
}
