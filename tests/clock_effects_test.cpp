#include <initializer_list>

#include "apps/clock/effects/effects.h"
#include <cassert>
#include <cstdio>
#include <cstdint>
#include <cstring>
static uint16_t storage[240*240+2];
static uint32_t hash(){uint32_t h=2166136261;for(unsigned i=1;i<=240*240;i++)h=(h^storage[i])*16777619;return h;}
int main(){
 storage[0]=0x1234;storage[240*240+1]=0xabcd;
 risc_display_surface_v1 s={1,storage+1,240,240,480,115200,5};
 assert(watch_boot_render(&s,0));
 for(unsigned i=1;i<=240*240;i++)assert(storage[i]==0);
 uint32_t prior=0;
 for(unsigned ms: {200u,600u,1100u,1600u,1800u}) {
  assert(watch_boot_render(&s,ms));assert(hash()!=prior);prior=hash();
  assert(storage[0]==0x1234&&storage[240*240+1]==0xabcd);
  unsigned ink=0;
  for(unsigned i=1;i<=240*240;i++){assert(storage[i]==0 || storage[i]==0xffff);ink+=storage[i]==0xffff;}
  assert(ink>0 && ink<240*240/2); // light, sparse foreground
  char path[80];snprintf(path,sizeof(path),"/tmp/watch-boot-%u.ppm",ms);FILE*f=fopen(path,"wb");assert(f);
  fprintf(f,"P6\n240 240\n255\n");for(unsigned i=1;i<=240*240;i++){unsigned char v=storage[i]?255:0;fputc(v,f);fputc(v,f);fputc(v,f);}fclose(f);
 }
 for(unsigned scan=0;scan<16;scan++){
  for(unsigned i=1;i<=240*240;i++)storage[i]=0x1234;
  assert(watch_ripple_render(&s,scan));
  if(scan==15)for(unsigned i=1;i<=240*240;i++)assert(storage[i]==0);
 }
 s.size_bytes=100;assert(!watch_boot_render(&s,100)&&!watch_ripple_render(&s,0));
 assert(storage[0]==0x1234&&storage[240*240+1]==0xabcd);
 puts("Copied boot frames and finite ripple endpoints/bounds passed");
}
