#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "apps/clock/nova/nova.h"
static uint8_t buffer[240*488+32];
int main(int argc,char**argv){
 assert(argc==2);for(unsigned test=0;test<5;test++) {
  memset(buffer,0xa5,sizeof(buffer));risc_display_surface_v1 s={1,buffer+16,240,240,488,240*488,RISC_DISPLAY_FORMAT_RGB565};
  assert(nova_watch_alarm_render(&s,test==1,test>=2&&test<=3,test==2,test==4,test==3,true));
  for(unsigned n=0;n<16;n++)assert(buffer[n]==0xa5&&buffer[sizeof(buffer)-1-n]==0xa5);
  for(unsigned y=0;y<240;y++)for(unsigned x=480;x<488;x++)assert(buffer[16+y*488+x]==0xa5);
  char name[1024];snprintf(name,sizeof(name),"%s/alarm-%u.ppm",argv[1],test);FILE*f=fopen(name,"wb");assert(f);fprintf(f,"P6\n240 240\n255\n");
  for(unsigned y=0;y<240;y++)for(unsigned x=0;x<240;x++){unsigned offset=16+y*488+x*2;uint16_t c=buffer[offset]|buffer[offset+1]<<8;uint8_t rgb[]={((c>>11)&31)*255/31,((c>>5)&63)*255/63,(c&31)*255/31};assert(fwrite(rgb,1,3,f)==3);}
  fclose(f);
 }
 puts("Pure alert renderer guards, stride padding and five states passed");
}
