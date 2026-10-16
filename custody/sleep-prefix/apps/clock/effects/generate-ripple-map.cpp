#include <cstdio>
#include <vector>
#include "reference/NativeVideoBootScrub.h"
int main(){
 using namespace NativeVideoBootScrub;
 std::vector<uint8_t> m(kMapBytes);
 for(unsigned y=0;y<kHeight;y+=kGrid)buildBand(m.data(),y);
 puts("/* Exact pinned T5 arrival field, portrait resample, two 4-bit values/byte. */\nstatic const uint8_t arrivals[240*240/2]={");
 for(unsigned y=0;y<240;y++){
  for(unsigned x=0;x<240;x+=2){
   unsigned a=m[((239-x)*540/240)*960+y*960/240];
   unsigned b=m[((238-x)*540/240)*960+y*960/240];
   printf("%u,",a|(b<<4));
  }
  puts("");
 }
 puts("};");
}
