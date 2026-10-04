#include <stdint.h>
#include <assert.h>
#include <limits.h>
int64_t __divdi3(int64_t,int64_t);
int main(void){
 int64_t n[]={INT64_MIN,INT64_MAX,-1000000001,-1,0,1,1000000001};
 int64_t d[]={INT64_MIN,INT64_MAX,-1000000000,-1,1,1000000,1000000000};
 for(unsigned i=0;i<7;i++)for(unsigned j=0;j<7;j++){
  if(n[i]==INT64_MIN&&d[j]==-1)continue;
  assert(__divdi3(n[i],d[j])==n[i]/d[j]);
 }
 uint64_t seed=1;
 for(unsigned i=0;i<10000;i++){
  seed=seed*6364136223846793005ull+1;int64_t a=(int64_t)seed;
  seed=seed*6364136223846793005ull+1;int64_t b=(int64_t)seed;
  if(b && !(a==INT64_MIN&&b==-1))assert(__divdi3(a,b)==a/b);
 }
}
