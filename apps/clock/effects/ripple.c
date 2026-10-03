/* T5S3 NativeVideoBootScrub command sequence, mapped to RGB565.
 * Caller reconstructs the outgoing frame before applying each scan.
 * Retain leaves it intact; ends with every pixel white. */
#include "effects.h"
#include "ripple-map.h"
bool watch_ripple_render(const risc_display_surface_v1 *s,uint32_t scan) {
 if(!s || !s->pixels || s->width!=240 || s->height!=240 || s->stride_bytes!=480 || s->size_bytes<115200 || s->pixel_format!=5) return false;
 uint16_t *p=s->pixels;
 for(unsigned i=0;i<240*240;i++)if(scan>=arrivals[i])p[i]=scan<arrivals[i]+3u?0:0xffff;
 return true;
}
