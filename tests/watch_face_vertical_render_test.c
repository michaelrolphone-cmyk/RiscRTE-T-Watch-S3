#define WATCH_FACE_RENDER_TEST 1
#include "apps/clock/nova/nova.c"
#include <assert.h>
#include <stdio.h>
static nova_watch_picker_cache cache,reference_cache;
static uint8_t actual[240*488+32],expected[240*480],page_pixels[240*480];
static const nova_watch_state fixture={.time={2026,10,4,0,10,42,18},.time_valid=true,.battery_valid=true,.battery_percent=84,.subsecond_ms=250,.animation_ms=42000};
int main(int argc,char**argv){
 int positions[4]={-108*256,-3*108*256,-2*108*256,-4*108*256};
 risc_display_surface_v1 a={0,actual+16,240,240,488,240*488,5},r={0,page_pixels,240,240,480,sizeof(page_pixels),5};
 const int offsets[]={48,0,-1,-24,-60,-90,-120,-150,-180,-216,-239,-240,-264,-720,-768,-840,-900,-959,-960,-1008};
 for(unsigned n=0;n<sizeof(offsets)/sizeof(offsets[0]);n++){
  int pos=offsets[n];memset(actual,0xa5,sizeof(actual));memset(expected,0,sizeof(expected));cache.valid_mask=0;
  face_test_calls=0;assert(nova_watch_picker_collections_render(&a,&fixture,23,pos*256,positions,NULL,24,256,&cache));assert(face_test_calls<=6);
  for(unsigned c=0;c<4;c++){
   int y0=(int)c*240+pos;if(y0>480)y0-=960;if(y0<-480)y0+=960;if(y0<=-240||y0>=240)continue;
   reference_cache.valid_mask=0;assert(nova_watch_picker_render(&r,&fixture,23,positions[c],watch_face_page_for(c),NULL,24,256,&reference_cache));
   for(int y=0;y<240;y++)if(y+y0>=0&&y+y0<240)memcpy(expected+(y+y0)*480,page_pixels+y*480,480);
  }
  for(unsigned y=0;y<240;y++){assert(!memcmp(actual+16+y*488,expected+y*480,480));for(unsigned x=480;x<488;x++)assert(actual[16+y*488+x]==0xa5);}
  for(unsigned i=0;i<16;i++)assert(actual[i]==0xa5&&actual[sizeof(actual)-i-1]==0xa5);
  nova_watch_state next=fixture;next.time.second++;next.subsecond_ms=900;next.animation_ms+=1000;
  face_test_calls=face_test_mask=0;assert(nova_watch_picker_collections_render(&a,&next,23,pos*256,positions,NULL,24,256,&cache));assert(face_test_calls<=1);
  int normalized=pos%960;if(normalized>0)normalized-=960;unsigned focus=(unsigned)((-normalized+120)/240)%4;
  unsigned id=watch_face_page_for((unsigned)focus)->ids[-positions[focus]/(108*256)];assert(face_test_mask==(1u<<id));
  if(argc>1){cache.valid_mask=0;assert(nova_watch_picker_collections_render(&a,&fixture,23,pos*256,positions,NULL,24,256,&cache));char path[512];snprintf(path,sizeof(path),"%s/vertical-%02u.rgb565",argv[1],n);FILE*f=fopen(path,"wb");assert(f);for(unsigned y=0;y<240;y++)assert(fwrite(actual+16+y*488,1,480,f)==480);fclose(f);}
 }
 /* Repeated bidirectional movement keeps every nonfocused card frozen and
  * never renders the unrelated selected global face23 behind the picker. */
 cache.valid_mask=0;
 for(unsigned pass=0;pass<2;pass++)for(int y=0;y<=720;y+=7){int pos=pass?-720+y:-y;face_test_mask=0;assert(nova_watch_picker_collections_render(&a,&fixture,23,pos*256,positions,NULL,24,256,&cache));assert(!(face_test_mask&(1u<<23)));face_test_calls=0;assert(nova_watch_picker_collections_render(&a,&fixture,23,pos*256,positions,NULL,24,256,&cache));assert(face_test_calls==1);}
 a.size_bytes--;assert(!nova_watch_picker_collections_render(&a,&fixture,23,0,positions,NULL,24,256,&cache));
 printf("Vertical production pixels equal clipped translated collections; guards preserved; only focus live, <=6 visible caches; cache bytes=%zu\n",sizeof(cache));
}
