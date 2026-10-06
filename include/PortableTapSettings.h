#ifndef PORTABLE_TAP_SETTINGS_V1_H
#define PORTABLE_TAP_SETTINGS_V1_H
/* Application policy in existing namespace 1, preserved by paired updates.
 * One checked record atomically stores Off and distinct sensor parameters.
 * Missing retains released defaults; corrupt/unreadable records fail closed
 * to crown/timer-only wake rather than silently re-enabling physical taps. */
#include "RiscKeyValueV1.h"
#include "PortableMotionTap.h"
#include <string.h>
#define PORTABLE_TAP_KEY "tap_wake"
#define PORTABLE_TAP_STORE_INSTANCE 1u
typedef struct { uint8_t enabled,bma423,bma456h,measured; } portable_tap_settings;
enum { PORTABLE_TAP_LOADED,PORTABLE_TAP_MISSING,PORTABLE_TAP_INVALID,PORTABLE_TAP_UNAVAILABLE };
static inline portable_tap_settings portable_tap_defaults(void) {
    return (portable_tap_settings){1,3,12,0};
}
static inline bool portable_tap_settings_valid(const portable_tap_settings *p) {
    return p && p->enabled<=1 && p->bma423<=7 && p->bma456h<=15 && p->measured<=3;
}
static inline bool portable_tap_store_valid(const risc_key_value_v1 *kv) {
    return kv && kv->api_version==1 && kv->struct_size>=sizeof(*kv) && kv->get && kv->put;
}
static inline uint16_t portable_tap_checksum(const uint8_t *bytes) {
    uint16_t crc=0xffff;
    for(unsigned i=0;i<6;i++){crc^=(uint16_t)bytes[i]<<8;for(unsigned j=0;j<8;j++)crc=(uint16_t)((crc<<1)^((crc&0x8000)?0x1021:0));}
    return crc;
}
static inline int portable_tap_load(const risc_key_value_v1 *kv,portable_tap_settings *p) {
    if(!p)return PORTABLE_TAP_INVALID;
    *p=portable_tap_defaults();p->enabled=0;
    if(!portable_tap_store_valid(kv))return PORTABLE_TAP_UNAVAILABLE;
    uint8_t bytes[8]={0};uint32_t length=0;
    int rc=kv->get(kv->context,PORTABLE_TAP_KEY,bytes,sizeof(bytes),&length);
    if(rc==RISC_KEY_VALUE_NOT_FOUND){p->enabled=1;return PORTABLE_TAP_MISSING;}
    if(rc!=RISC_KEY_VALUE_OK)return rc==RISC_KEY_VALUE_BUFFER_SMALL?PORTABLE_TAP_INVALID:PORTABLE_TAP_UNAVAILABLE;
    portable_tap_settings decoded={bytes[2],bytes[3],bytes[4],bytes[5]};
    uint16_t crc=portable_tap_checksum(bytes);
    if(length!=sizeof(bytes) || bytes[0]!=0x57 || bytes[1]!=1 || !portable_tap_settings_valid(&decoded) ||
       bytes[6]!=(uint8_t)crc || bytes[7]!=(uint8_t)(crc>>8))return PORTABLE_TAP_INVALID;
    *p=decoded;return PORTABLE_TAP_LOADED;
}
static inline bool portable_tap_save(const risc_key_value_v1 *kv,const portable_tap_settings *p) {
    if(!portable_tap_store_valid(kv) || !portable_tap_settings_valid(p))return false;
    uint8_t bytes[8]={0x57,1,p->enabled,p->bma423,p->bma456h,p->measured,0,0};
    uint16_t crc=portable_tap_checksum(bytes);bytes[6]=(uint8_t)crc;bytes[7]=(uint8_t)(crc>>8);
    if(kv->put(kv->context,PORTABLE_TAP_KEY,bytes,sizeof(bytes))!=RISC_KEY_VALUE_OK)return false;
    portable_tap_settings observed;
    return portable_tap_load(kv,&observed)==PORTABLE_TAP_LOADED &&
        observed.enabled==p->enabled && observed.bma423==p->bma423 &&
        observed.bma456h==p->bma456h && observed.measured==p->measured;
}
static inline uint16_t portable_tap_value(const portable_tap_settings *p,uint16_t profile) {
    return profile==TWATCH_TAP_BMA423?p->bma423:p->bma456h;
}

#endif
