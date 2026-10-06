#pragma once
#include "bootstrap/AppDataBackend.h"
// Presence and authority only. Admission and Clock must not perform app-data
// I/O; the owner repositories exercise the actual filesystem consumers.
static RiscBoot::AppDataBackend admissionAppData(unsigned* calls) {
  return {calls,
    [](void* c,uint32_t,const char*,uint32_t*,uint64_t*)->int32_t {
      ++*static_cast<unsigned*>(c);return RISC_APP_DATA_UNAVAILABLE;
    },
    [](void* c,uint32_t,const char*,uint64_t,void*,uint32_t,uint32_t*,uint64_t*)->int32_t {
      ++*static_cast<unsigned*>(c);return RISC_APP_DATA_UNAVAILABLE;
    },
    [](void* c,uint32_t,const char*,uint64_t,const void*,uint32_t)->int32_t {
      ++*static_cast<unsigned*>(c);return RISC_APP_DATA_UNAVAILABLE;
    },
    [](void*) {return true;}
  };
}
