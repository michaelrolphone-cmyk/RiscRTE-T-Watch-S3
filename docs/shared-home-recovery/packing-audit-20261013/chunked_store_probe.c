/* Measurement-only SPIFFS writer/readback using existing local ESP-IDF sources.
 * Does not select product geometry or emit firmware. */
#include "spiffs.h"
#include "spiffs_nucleus.h"
#include <assert.h>
#include <inttypes.h>
static unsigned char *image;
static size_t image_size;
static uint64_t hal_writes, hal_erases;
void spiffs_api_lock(spiffs *fs) {(void)fs;}
void spiffs_api_unlock(spiffs *fs) {(void)fs;}
static s32_t rd(spiffs *fs,u32_t a,u32_t n,u8_t *p) {
 (void)fs; assert((uint64_t)a+n<=image_size); memcpy(p,image+a,n); return SPIFFS_OK;
}
static s32_t wr(spiffs *fs,u32_t a,u32_t n,u8_t *p) {
 (void)fs; assert((uint64_t)a+n<=image_size);
 for (u32_t i=0;i<n;i++) image[a+i]&=p[i];
 ++hal_writes; return SPIFFS_OK;
}
static s32_t er(spiffs *fs,u32_t a,u32_t n) {
 (void)fs; assert((uint64_t)a+n<=image_size); memset(image+a,255,n); ++hal_erases; return SPIFFS_OK;
}
int main(int argc,char **argv) {
 assert(argc==5);
 image_size=strtoul(argv[1],NULL,0); assert(image_size%4096==0 && image_size<=0x550000);
 image=malloc(image_size); assert(image); memset(image,255,image_size);
 spiffs fs={0}; spiffs_config cfg={0};
 cfg.hal_read_f=rd; cfg.hal_write_f=wr; cfg.hal_erase_f=er; cfg.phys_addr=0;
 cfg.phys_size=image_size; cfg.phys_erase_block=4096; cfg.log_block_size=4096; cfg.log_page_size=256;
 unsigned char work[512]; unsigned max_files=4;
 void *fds=calloc(max_files,sizeof(spiffs_fd));
 size_t cs=sizeof(spiffs_cache)+max_files*(sizeof(spiffs_cache_page)+256);
 void *cache=calloc(cs,1); assert(fds&&cache);
 s32_t result=SPIFFS_mount(&fs,&cfg,work,fds,max_files*sizeof(spiffs_fd),cache,cs,0);
 assert(result==SPIFFS_ERR_NOT_A_FS);
 assert(SPIFFS_format(&fs)==SPIFFS_OK);
 assert(SPIFFS_mount(&fs,&cfg,work,fds,max_files*sizeof(spiffs_fd),cache,cs,0)==SPIFFS_OK);
 FILE *list=fopen(argv[3],"r"); assert(list);
 char names[256][128], host[2048], target[160], failed_name[128]="";
 unsigned completed=0, requested=0; int failed=0; unsigned char data[8192],reference[8192];
 while (fscanf(list,"%127s",names[requested])==1) { requested++; assert(requested<256); }
 fclose(list);
 for (unsigned i=0;i<requested;i++) {
  snprintf(host,sizeof(host),"%s/%.127s",argv[2],names[i]);
  snprintf(target,sizeof(target),"/%.127s",names[i]);
  FILE *input=fopen(host,"rb"); assert(input);
  spiffs_file fd=SPIFFS_open(&fs,target,SPIFFS_O_CREAT|SPIFFS_O_TRUNC|SPIFFS_O_RDWR,0);
  if(fd<0) {failed=SPIFFS_errno(&fs); strcpy(failed_name,names[i]); fclose(input); break;}
  size_t n;
  while ((n=fread(data,1,sizeof(data),input))>0) {
   s32_t written=SPIFFS_write(&fs,fd,data,n);
   if(written!=(s32_t)n) {failed=SPIFFS_errno(&fs); if(!failed)failed=-19999; strcpy(failed_name,names[i]); break;}
  }
  assert(!ferror(input)); fclose(input);
  s32_t closed=SPIFFS_close(&fs,fd);
  if(!failed && closed!=SPIFFS_OK) {failed=SPIFFS_errno(&fs); strcpy(failed_name,names[i]);}
  if(failed)break;
  completed++;
 }
 SPIFFS_unmount(&fs);
 assert(SPIFFS_mount(&fs,&cfg,work,fds,max_files*sizeof(spiffs_fd),cache,cs,0)==SPIFFS_OK);
 unsigned verified=0;
 for (unsigned i=0;i<completed;i++) {
  snprintf(host,sizeof(host),"%s/%.127s",argv[2],names[i]);
  snprintf(target,sizeof(target),"/%.127s",names[i]);
  FILE *input=fopen(host,"rb"); assert(input);
  spiffs_file fd=SPIFFS_open(&fs,target,SPIFFS_O_RDONLY,0); assert(fd>=0);
  for (;;) {
   size_t n=fread(reference,1,sizeof(reference),input);
   s32_t got=SPIFFS_read(&fs,fd,data,sizeof(data));
   assert(got>=0 && (size_t)got==n); assert(memcmp(data,reference,n)==0);
   if(!n)break;
  }
  assert(!ferror(input)); fclose(input); assert(SPIFFS_close(&fs,fd)==SPIFFS_OK); verified++;
 }
 unsigned long live=0,deleted=0,freepages=0,freeblocks=0,liveblocks=0;
 for(size_t b=0;b<image_size/4096;b++) {
  unsigned free_in_block=0,live_in_block=0;
  for(unsigned e=0;e<15;e++) {
   unsigned obj=image[b*4096+e*2]|(image[b*4096+e*2+1]<<8);
   if(obj==65535) {freepages++;free_in_block++;}
   else if(obj==0)deleted++;
   else {live++;live_in_block++;}
  }
  if(free_in_block==15)freeblocks++;
  if(live_in_block)liveblocks++;
 }
 printf("{\"requested_files\":%u,\"completed_files\":%u,\"remount_readback_files\":%u,"
 "\"error\":%d,\"failed_name\":\"%s\",\"image_bytes\":%zu,\"chunk_bytes\":8192,"
 "\"live_pages\":%lu,\"deleted_pages\":%lu,\"free_pages\":%lu,\"empty_blocks\":%lu,"
 "\"blocks_containing_live_pages\":%lu,\"fs_free_blocks\":%u,\"fs_allocated_pages\":%u,"
 "\"fs_deleted_pages\":%u,\"hal_writes\":%"PRIu64",\"hal_erases\":%"PRIu64"}\n",
 requested,completed,verified,failed,failed_name,image_size,live,deleted,freepages,freeblocks,liveblocks,
 fs.free_blocks,fs.stats_p_allocated,fs.stats_p_deleted,hal_writes,hal_erases);
 SPIFFS_unmount(&fs);
 FILE *output=fopen(argv[4],"wb"); assert(output);
 assert(fwrite(image,1,image_size,output)==image_size); assert(fclose(output)==0);
 free(fds);free(cache);free(image);return 0;
}
