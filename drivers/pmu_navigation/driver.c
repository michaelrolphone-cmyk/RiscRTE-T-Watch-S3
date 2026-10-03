/* Logical navigation bridge. The PMU ELF retains sole ownership of registers,
 * rail policy and key IRQ acknowledgement; this provider owns no hardware. */
#include "twatch_support.h"
#include "twatch_caps.h"
#include "RiscInputNavigationV1.h"
static const twatch_pmu_api_v1 *pmu;
static bool started,down,suppressed;
static bool reset(void *c){
 (void)c;down=false;uint32_t discard=0;
 return started && pmu->key_events(pmu->base.context,&discard);
}
static bool poll(void*c,risc_input_navigation_frame_v1*out){
 (void)c;if(!started||!out)return false;*out=(risc_input_navigation_frame_v1){0};
 if(suppressed)return true;
 uint32_t e=0;if(!pmu->key_events(pmu->base.context,&e)){down=false;return false;}
 if(e&TWATCH_PMU_KEY_DOWN)down=true;
 if(e&TWATCH_PMU_KEY_UP){
  if(down && (e&TWATCH_PMU_KEY_SHORT))out->pressed=out->released=RISC_NAV_BACK;
  down=false;
 }
 return true;
}
static bool foreground(void*c,const risc_input_foreground_v1*claims,size_t n){
 (void)c;if(!started)return false;suppressed=true;down=false;
 if(n>RISC_INPUT_NAVIGATION_MAX_FOREGROUND || (n&&!claims))return false;
 for(size_t i=0;i<n;i++)if(!claims[i].capability||!claims[i].api_version)return false;
 suppressed=false;
 for(size_t i=0;i<n;i++)if(twatch_equal(claims[i].capability,"input.navigation"))suppressed=true;
 return reset(NULL);
}
static bool start(const risc_provider_dependency_v1*d,size_t n){
 if(started)return false;
 pmu=tw_dep(d,n,"board.battery",sizeof(*pmu));
 if(!pmu||!pmu->key_events)return false;
 started=true;down=false;suppressed=false;return reset(NULL);
}
static bool quiesce(void){started=down=suppressed=false;pmu=NULL;return true;}
static const risc_input_navigation_api_v1 api={1,sizeof(api),NULL,poll,foreground,reset};
TW_DRIVER("pmu-navigation","input.navigation",1,api)
