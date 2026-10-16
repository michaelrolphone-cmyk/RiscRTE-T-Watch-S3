#pragma once
#include <stdint.h>
#include "names.h"
#define WATCH_FACE_CATEGORY_COUNT 5u
typedef struct { const uint8_t *ids; unsigned count; const char *name; } watch_face_page;
/* Stable global IDs preserve existing watch_face records. Categories are only
 * a browsing view; changing their order never changes persisted identity. */
static const uint8_t watch_face_analog[]={1,7,13};
static const uint8_t watch_face_large[]={0,3,5,8,10,12,14,15};
#ifdef WATCH_CONTEXTS_CLIENT
static const uint8_t watch_face_compact[]={2,4,6,9,11,33};
#else
static const uint8_t watch_face_compact[]={2,4,6,9,11};
#endif
static const uint8_t watch_face_calendar[]={16,17,18,19,20,21,22,23};
static const uint8_t watch_face_schedule[]={24,25,26,27,28,29,30,31,32};
static const watch_face_page watch_face_pages[]={
    {watch_face_analog,3,"ANALOG"},{watch_face_large,8,"LARGE DIGITAL"},
    {watch_face_compact,sizeof(watch_face_compact)/sizeof(*watch_face_compact),"COMPACT DIGITAL"},{watch_face_calendar,8,"CALENDAR"},
    {watch_face_schedule,9,"SCHEDULE"}
};
static inline const watch_face_page*watch_face_page_for(unsigned category){return &watch_face_pages[category<WATCH_FACE_CATEGORY_COUNT?category:0];}
static inline unsigned watch_face_category_for(unsigned id){
    for(unsigned c=0;c<WATCH_FACE_CATEGORY_COUNT;c++)for(unsigned i=0;i<watch_face_pages[c].count;i++)if(watch_face_pages[c].ids[i]==id)return c;
    return 1;
}
static inline unsigned watch_face_index_for(unsigned category,unsigned id){
    const watch_face_page*p=watch_face_page_for(category);for(unsigned i=0;i<p->count;i++)if(p->ids[i]==id)return i;return 0;
}
