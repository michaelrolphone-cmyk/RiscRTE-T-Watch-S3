#pragma once
/* Shared app-owned display preference. Runtime stores opaque bytes only.
 * Namespace 1 is the existing explicit app-settings grant. Loading a missing,
 * malformed or unavailable record selects 12-hour without writing defaults. */
#include "RiscKeyValueV1.h"
#include <stdbool.h>
#include <stdint.h>
#define PORTABLE_TIME_FORMAT_12 0u
#define PORTABLE_TIME_FORMAT_24 1u
#define PORTABLE_TIME_FORMAT_KEY "time_format"
#define PORTABLE_TIME_FORMAT_STORE_INSTANCE 1u
enum { PORTABLE_TIME_FORMAT_LOADED=0, PORTABLE_TIME_FORMAT_MISSING=1,
       PORTABLE_TIME_FORMAT_INVALID=2, PORTABLE_TIME_FORMAT_UNAVAILABLE=3 };
static inline bool portable_time_format_api_valid(const risc_key_value_v1 *kv) {
    return kv && kv->api_version==RISC_KEY_VALUE_API_V1 &&
        kv->struct_size>=sizeof(*kv) && kv->get;
}
static inline int portable_time_format_load(const risc_key_value_v1 *kv,unsigned *mode) {
    if(!mode)return PORTABLE_TIME_FORMAT_INVALID;
    *mode=PORTABLE_TIME_FORMAT_12;
    if(!portable_time_format_api_valid(kv))return PORTABLE_TIME_FORMAT_UNAVAILABLE;
    uint8_t data[4]={0};uint32_t size=0;
    int32_t rc=kv->get(kv->context,PORTABLE_TIME_FORMAT_KEY,data,sizeof(data),&size);
    if(rc==RISC_KEY_VALUE_NOT_FOUND)return PORTABLE_TIME_FORMAT_MISSING;
    if(rc==RISC_KEY_VALUE_BUFFER_SMALL)return PORTABLE_TIME_FORMAT_INVALID;
    if(rc!=RISC_KEY_VALUE_OK)return PORTABLE_TIME_FORMAT_UNAVAILABLE;
    if(size!=sizeof(data) || data[0]!=0x54 || data[1]!=1 || data[2]>PORTABLE_TIME_FORMAT_24 ||
       data[3]!=(uint8_t)(data[2]^0xa5u))return PORTABLE_TIME_FORMAT_INVALID;
    *mode=data[2];return PORTABLE_TIME_FORMAT_LOADED;
}
/* Save only an explicit change. Failure never claims persistence: the KV ABI
 * permits IO after a commit, so callers keep their last confirmed display and
 * expose an unconfirmed-save message, rather than attempt unsafe rollback. */
static inline bool portable_time_format_save(const risc_key_value_v1 *kv,unsigned mode) {
    if(!portable_time_format_api_valid(kv) || !kv->put || mode>PORTABLE_TIME_FORMAT_24)return false;
    unsigned current;
    int loaded=portable_time_format_load(kv,&current);
    if(loaded==PORTABLE_TIME_FORMAT_UNAVAILABLE)return false;
    if(current==mode)return true; /* Missing/invalid 12h needs no repair write. */
    const uint8_t data[]={0x54,1,(uint8_t)mode,(uint8_t)(mode^0xa5u)};
    if(kv->put(kv->context,PORTABLE_TIME_FORMAT_KEY,data,sizeof(data))!=RISC_KEY_VALUE_OK)return false;
    return portable_time_format_load(kv,&current)==PORTABLE_TIME_FORMAT_LOADED && current==mode;
}
