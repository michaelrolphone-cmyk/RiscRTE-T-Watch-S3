/* Real shared host with four dependencies, matching the Watch product. */
#define main baseline_main
#include "host_test.c"
#undef main
#include "RiscSceneComponentsV1.h"
int main(void){
 driver=t5_driver_get(2);assert(driver);api=driver->capability;
 risc_provider_dependency_v1 deps[]={{"display.output",1,&disp},{"input.touch.raw",1,&raw},{"platform.clock",1,&clk},{"ui.presentation-profile",1,&prof}};
 assert(driver->start(deps,4));const risc_scene_components_api_v1 *c=risc_scene_components_get_v1(api);assert(c);
 risc_components_document_v1 d={.api_version=1,.struct_size=sizeof(d),.revision=1,.root=1,.route_count=1,.node_count=2,.screen_key=1};
 d.routes[0]=(risc_scene_route_v1){1,99,"CHECKLIST"};d.nodes[0]=(risc_scene_node_v1){.id=1,.route=1,.kind=RISC_COMPONENT_CHECK_ROW,.action=10,.maximum=1,.step=1,.label="TEST TASK"};
 d.nodes[1]=(risc_scene_node_v1){.id=2,.route=1,.kind=RISC_COMPONENT_HEADER_ACTION,.action=77};
 expected_intent=RISC_DISPLAY_PRESENT_LOW_LATENCY;
 assert(c->open(NULL,&d,NULL,&session)==0);settle();touch_tap(25,95);
 risc_scene_event_v1 e;assert(tick(&e)==0&&e.node==1&&e.kind==RISC_SCENE_VALUE_EVENT&&e.action==10&&e.value==1);
 d.revision++;d.nodes[0].value=1;assert(c->update(NULL,session,&d)==0);settle();touch_tap(24,55);
 assert(tick(&e)==0&&e.action==99);finish();puts("Watch actual scene host: touch checkbox, header back and clean teardown PASS");return 0;
}
