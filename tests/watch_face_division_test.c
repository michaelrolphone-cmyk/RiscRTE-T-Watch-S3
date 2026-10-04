#include <stdint.h>
#include <stdio.h>
#include <assert.h>
uint64_t __udivdi3(uint64_t,uint64_t),__umoddi3(uint64_t,uint64_t);
int64_t __divdi3(int64_t,int64_t),__moddi3(int64_t,int64_t);
int main(void){
 const uint64_t edge[]={0,1,2,UINT32_MAX,1ULL<<32,INT64_MAX,1ULL<<63,UINT64_MAX};
 uint64_t random=123456789;
 for(unsigned i=0;i<20000;i++) {
  random=random*6364136223846793005ULL+1;uint64_t n=i<64?edge[i%8]:random;
  random=random*6364136223846793005ULL+1;uint64_t d=i<64?edge[i/8]:random;
  if(!d){assert(__udivdi3(n,d)==0&&__umoddi3(n,d)==0);continue;}
  assert(__udivdi3(n,d)==n/d&&__umoddi3(n,d)==n%d);
  int64_t sn=(int64_t)n,sd=(int64_t)d;if(sn==INT64_MIN&&sd==-1)continue;
  assert(__divdi3(sn,sd)==sn/sd&&__moddi3(sn,sd)==sn%sd);
 }
 puts("PIC signed/unsigned64 division/remainder:20,000 edge/random cases passed");
}
