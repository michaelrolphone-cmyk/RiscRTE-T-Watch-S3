#include "spiffs.h"
#include "spiffs_nucleus.h"
#include <assert.h>
#include <inttypes.h>
static unsigned char*image;static size_t image_size;
static uint64_t calls,bytes,writes,erases;
void spiffs_api_lock(spiffs*fs){(void)fs;}
void spiffs_api_unlock(spiffs*fs){(void)fs;}
static s32_t rd(spiffs*fs,u32_t a,u32_t n,u8_t*p){(void)fs;assert((uint64_t)a+n<=image_size);memcpy(p,image+a,n);++calls;bytes+=n;return SPIFFS_OK;}
static s32_t wr(spiffs*fs,u32_t a,u32_t n,u8_t*p){(void)fs;(void)a;(void)n;(void)p;++writes;assert(!"unexpected write");return -1;}
static s32_t er(spiffs*fs,u32_t a,u32_t n){(void)fs;(void)a;(void)n;++erases;assert(!"unexpected erase");return -1;}
static void counters(const char*stage,const char*path,unsigned long total){printf("%s,%s,%lu,%"PRIu64",%"PRIu64"\n",stage,path,total,calls,bytes);calls=bytes=0;}
int main(int argc,char**argv){
 assert(argc==6);FILE*f=fopen(argv[1],"rb");assert(f);fseek(f,0,SEEK_END);image_size=ftell(f);rewind(f);image=malloc(image_size);assert(image);assert(fread(image,1,image_size,f)==image_size);fclose(f);
 const unsigned max_files=(unsigned)atoi(argv[3]);assert(max_files&&max_files<=32);
 spiffs fs={0};spiffs_config cfg={0};cfg.hal_read_f=rd;cfg.hal_write_f=wr;cfg.hal_erase_f=er;cfg.phys_addr=0;cfg.phys_size=image_size;cfg.phys_erase_block=4096;cfg.log_block_size=4096;cfg.log_page_size=256;
 unsigned char work[512];void*fds=calloc(max_files,sizeof(spiffs_fd));size_t cs=sizeof(spiffs_cache)+max_files*(sizeof(spiffs_cache_page)+256);void*cache=calloc(cs,1);assert(fds&&cache);
 assert(SPIFFS_mount(&fs,&cfg,work,fds,max_files*sizeof(spiffs_fd),cache,cs,0)==SPIFFS_OK);counters("mount","",0);
 f=fopen(argv[2],"r");assert(f);char path[256];unsigned chunk=0;
 while(fscanf(f,"%u %255s",&chunk,path)==2){
  spiffs_file fd=SPIFFS_open(&fs,path,SPIFFS_O_RDONLY,0);if(fd<0){fprintf(stderr,"open failed %s %d\n",path,SPIFFS_errno(&fs));return 2;}counters("open",path,0);
  if(chunk==4096){if(argc>=5){spiffs_stat info;assert(!SPIFFS_fstat(&fs,fd,&info));assert(info.size>0);counters("fstat",path,0);}else{assert(SPIFFS_lseek(&fs,fd,0,SPIFFS_SEEK_END)>0);assert(SPIFFS_lseek(&fs,fd,0,SPIFFS_SEEK_SET)==0);counters("seek",path,0);}}
  char expected_path[1024];assert(snprintf(expected_path,sizeof(expected_path),"%s%s",argv[5],path)<(int)sizeof(expected_path));
  FILE* expected=fopen(expected_path,"rb");assert(expected);
  unsigned char reference[4096];
  unsigned char data[4096];unsigned long total=0;assert(chunk<=sizeof(data));
  for(;;){s32_t n=SPIFFS_read(&fs,fd,data,chunk);assert(n>=0);assert(fread(reference,1,chunk,expected)==(size_t)n);assert(!memcmp(reference,data,(size_t)n));total+=n;if(n==0)break;}
  assert(feof(expected)&&!ferror(expected));assert(!fclose(expected));
  counters("read",path,total);assert(SPIFFS_close(&fs,fd)==SPIFFS_OK);counters("close",path,0);
 }
 fclose(f);SPIFFS_unmount(&fs);assert(!writes&&!erases);free(fds);free(cache);free(image);return 0;
}
