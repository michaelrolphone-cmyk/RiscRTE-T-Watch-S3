#include "runtime_boot_confirm.h"
#include <assert.h>
#include <stdint.h>
#ifdef UPDATE_CANONICAL_ABI
_Static_assert(offsetof(risc_runtime_api_v1,confirm_boot)==RISC_RUNTIME_CAPABILITIES_V1_SIZE,"append-only callback offset");
_Static_assert(RISC_RUNTIME_BOOT_CONFIRM_V1_SIZE==RISC_RUNTIME_CAPABILITIES_V1_SIZE+sizeof(void(*)(void)),"complete callback boundary");
#else
_Static_assert(sizeof(risc_runtime_api_v1)==RISC_RUNTIME_CAPABILITIES_V1_SIZE,"unchanged frozen SDK prefix");
#endif
#ifdef __XTENSA__
_Static_assert(RISC_RUNTIME_CAPABILITIES_V1_SIZE==32,"target frozen prefix is 32 bytes");
_Static_assert(sizeof(bool(*)(void))==4,"target callback is 4 bytes");
#ifdef UPDATE_CANONICAL_ABI
_Static_assert(RISC_RUNTIME_BOOT_CONFIRM_V1_SIZE==36,"target optional suffix ends at 36 bytes");
#endif
bool update_abi_target_probe(const risc_runtime_api_v1* rt){return watch_confirm_paired_boot(rt);}
#else
#include <sys/mman.h>
#include <unistd.h>
#include <stdio.h>
static unsigned calls;
static bool result=true;
static bool confirm(void){++calls;return result;}
int main(void){
  const size_t prefix=RISC_RUNTIME_CAPABILITIES_V1_SIZE,full=prefix+sizeof(bool(*)(void));
  size_t page=(size_t)sysconf(_SC_PAGESIZE);
  unsigned char* memory=mmap(NULL,page*2,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE,-1,0);
  assert(memory!=MAP_FAILED&&mprotect(memory+page,page,PROT_NONE)==0);
  assert(!watch_confirm_paired_boot(NULL));
  // Old/truncated tables physically end at the inaccessible next page. Even
  // an advertised partial suffix must never cause a callback read.
  risc_runtime_api_v1* old=(risc_runtime_api_v1*)(memory+page-prefix);
  for(uint32_t size=0;size<full;++size){memset(old,0,prefix);old->api_version=1;old->struct_size=size;assert(!watch_confirm_paired_boot(old));}
  old->api_version=2;old->struct_size=(uint32_t)full;assert(!watch_confirm_paired_boot(old));assert(!calls);
  risc_runtime_api_v1* complete=(risc_runtime_api_v1*)(memory+page-full);
  memset(complete,0,full);complete->api_version=1;complete->struct_size=(uint32_t)full;
  assert(!watch_confirm_paired_boot(complete)&&!calls);
  bool (*fn)(void)=confirm;memcpy((unsigned char*)complete+prefix,&fn,sizeof(fn));
  assert(watch_confirm_paired_boot(complete)&&calls==1);
  result=false;assert(!watch_confirm_paired_boot(complete)&&calls==2);
  complete->api_version=0;assert(!watch_confirm_paired_boot(complete)&&calls==2);
  assert(munmap(memory,page*2)==0);puts("Append-only Clock callback ABI and guard-page no-overread PASS");return 0;
}
#endif
