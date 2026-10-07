#ifndef PORTABLE_SLEEP_POLICY_H
#define PORTABLE_SLEEP_POLICY_H
/* Shared ELF policy only. Runtime persists opaque bytes and knows no mode.
 * Missing, unknown, malformed or unreadable records always choose Hybrid.
 * Namespace selection comes from the deployment's explicit app grant. */
#include "RiscKeyValueV1.h"
#include <stdbool.h>
#include <stdint.h>
#define PORTABLE_SLEEP_LIGHT 0u
#define PORTABLE_SLEEP_DEEP 1u
#define PORTABLE_SLEEP_HYBRID 2u
#define PORTABLE_SLEEP_LIGHT_MS 300000u
#define PORTABLE_SLEEP_IDLE_MS 60000u
#define PORTABLE_SLEEP_KEY "sleep_mode"
#define PORTABLE_SLEEP_STORE_INSTANCE 1u
enum { PORTABLE_SLEEP_LOADED=0, PORTABLE_SLEEP_MISSING=1,
       PORTABLE_SLEEP_INVALID=2, PORTABLE_SLEEP_UNAVAILABLE=3 };
static inline bool portable_sleep_api_valid(const risc_key_value_v1 *kv) {
    return kv && kv->api_version==RISC_KEY_VALUE_API_V1 &&
        kv->struct_size>=sizeof(*kv) && kv->get && kv->put;
}
static inline int portable_sleep_load(const risc_key_value_v1 *kv,unsigned *mode) {
    if(!mode)return PORTABLE_SLEEP_INVALID;
    *mode=PORTABLE_SLEEP_HYBRID;
    if(!portable_sleep_api_valid(kv))return PORTABLE_SLEEP_UNAVAILABLE;
    uint8_t data[4]={0};uint32_t size=0;
    int32_t rc=kv->get(kv->context,PORTABLE_SLEEP_KEY,data,sizeof(data),&size);
    if(rc==RISC_KEY_VALUE_NOT_FOUND)return PORTABLE_SLEEP_MISSING;
    if(rc==RISC_KEY_VALUE_BUFFER_SMALL)return PORTABLE_SLEEP_INVALID;
    if(rc!=RISC_KEY_VALUE_OK)return PORTABLE_SLEEP_UNAVAILABLE;
    if(size!=sizeof(data) || data[0]!=0x53 || data[1]!=1 || data[2]>PORTABLE_SLEEP_HYBRID ||
       data[3]!=(uint8_t)(data[2]^0xa5u))return PORTABLE_SLEEP_INVALID;
    *mode=data[2];return PORTABLE_SLEEP_LOADED;
}
static inline bool portable_sleep_save(const risc_key_value_v1 *kv,unsigned mode) {
    if(!portable_sleep_api_valid(kv) || mode>PORTABLE_SLEEP_HYBRID)return false;
    unsigned current;
    if(portable_sleep_load(kv,&current)==PORTABLE_SLEEP_LOADED && current==mode)return true;
    const uint8_t data[]={0x53,1,(uint8_t)mode,(uint8_t)(mode^0xa5u)};
    if(kv->put(kv->context,PORTABLE_SLEEP_KEY,data,sizeof(data))!=RISC_KEY_VALUE_OK)return false;
    return portable_sleep_load(kv,&current)==PORTABLE_SLEEP_LOADED && current==mode;
}

/* App-owned timer preferences share namespace 1 with Settings/Quick Controls.
 * Defaults preserve the accepted 60-second idle / five-minute Hybrid policy.
 * Each independent record lets manual edits change one timer without restoring
 * the other. Seconds are bounded and encoded explicitly, never native structs. */
#define PORTABLE_SLEEP_IDLE_KEY "sleep_idle"
#define PORTABLE_SLEEP_DEEP_KEY "sleep_deep"
static inline int portable_sleep_timer_load(const risc_key_value_v1 *kv,bool deep,uint32_t *milliseconds) {
    if(!milliseconds)return PORTABLE_SLEEP_INVALID;
    *milliseconds=deep?PORTABLE_SLEEP_LIGHT_MS:PORTABLE_SLEEP_IDLE_MS;
    if(!portable_sleep_api_valid(kv))return PORTABLE_SLEEP_UNAVAILABLE;
    uint8_t data[5]={0};uint32_t size=0;
    int32_t rc=kv->get(kv->context,deep?PORTABLE_SLEEP_DEEP_KEY:PORTABLE_SLEEP_IDLE_KEY,data,sizeof(data),&size);
    if(rc==RISC_KEY_VALUE_NOT_FOUND)return PORTABLE_SLEEP_MISSING;
    if(rc==RISC_KEY_VALUE_BUFFER_SMALL)return PORTABLE_SLEEP_INVALID;
    if(rc!=RISC_KEY_VALUE_OK)return PORTABLE_SLEEP_UNAVAILABLE;
    unsigned seconds=(unsigned)data[2]|((unsigned)data[3]<<8);
    if(size!=sizeof(data)||data[0]!=0x54||data[1]!=1||seconds<(deep?60u:5u)||seconds>3600||
       data[4]!=(uint8_t)(data[2]^data[3]^0xa5u))return PORTABLE_SLEEP_INVALID;
    *milliseconds=seconds*1000u;return PORTABLE_SLEEP_LOADED;
}
static inline bool portable_sleep_timer_save(const risc_key_value_v1 *kv,bool deep,uint32_t milliseconds) {
    if(!portable_sleep_api_valid(kv)||milliseconds<(deep?60000u:5000u)||milliseconds>3600000u||milliseconds%1000u)return false;
    uint32_t current=0;
    if(portable_sleep_timer_load(kv,deep,&current)==PORTABLE_SLEEP_LOADED&&current==milliseconds)return true;
    unsigned seconds=milliseconds/1000u;
    const uint8_t data[]={0x54,1,(uint8_t)seconds,(uint8_t)(seconds>>8),(uint8_t)(seconds^(seconds>>8)^0xa5u)};
    int32_t rc=kv->put(kv->context,deep?PORTABLE_SLEEP_DEEP_KEY:PORTABLE_SLEEP_IDLE_KEY,data,sizeof(data));
    return (rc==RISC_KEY_VALUE_OK||rc==RISC_KEY_VALUE_IO)&&
        portable_sleep_timer_load(kv,deep,&current)==PORTABLE_SLEEP_LOADED&&current==milliseconds;
}

#endif /* PORTABLE_SLEEP_POLICY_H */
