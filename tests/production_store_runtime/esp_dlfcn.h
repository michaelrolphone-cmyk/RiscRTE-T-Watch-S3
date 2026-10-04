#pragma once
#include <dlfcn.h>
#include <cstdio>
#include <cstdlib>
#include <unistd.h>
// Host dlopen caches paths/inodes. Each driver instance needs independent BSS,
// including the two production I2C instances selected from identical bytes.
extern "C" void production_test_loading(const char* path);
extern "C" void production_test_loaded(void* module);
extern "C" void production_test_unloading(void* module);
inline void* esp_dlopen_instance(const char* path) {
  production_test_loading(path);
  FILE* input=fopen(path,"rb");if(!input)return nullptr;
  char temporary[]="/tmp/watch-production-module-XXXXXX";
  int fd=mkstemp(temporary);if(fd<0){fclose(input);return nullptr;}
  FILE* output=fdopen(fd,"wb");bool ok=output!=nullptr;size_t total=0;
  if(output){char buffer[4096];size_t count;
    while((count=fread(buffer,1,sizeof(buffer),input))!=0){
      total+=count;
      if(total>8*1024*1024||fwrite(buffer,1,count,output)!=count){ok=false;break;}
    }
    ok=ok&&!ferror(input);if(fclose(output))ok=false;
  }else close(fd);
  fclose(input);
  void* module=ok?dlopen(temporary,RTLD_NOW|RTLD_LOCAL):nullptr;
  if(!module)fprintf(stderr,"dlopen %s: %s\n",path,dlerror());
  unlink(temporary);production_test_loaded(module);return module;
}
inline int production_test_dlclose(void* module){
  production_test_unloading(module);return dlclose(module);
}
inline void* production_test_dlopen(const char* path,int flags){
  production_test_loading(path);void* module=dlopen(path,flags);
  production_test_loaded(module);return module;
}
#define dlopen production_test_dlopen
#define dlclose production_test_dlclose
