/* Actual generated deployment catalog, with the shared adapter's established
 * lowest-provider fixtures. Enumerate and launch every delivered entry. */
#define main previous_fixture_main
#define portable_catalog old_fixture_catalog
#define portable_catalog_count old_fixture_count
#include "portable_adapter_test.c"
#undef main
#undef portable_catalog
#undef portable_catalog_count
extern const t5_app_manifest_t portable_catalog[];
extern const unsigned portable_catalog_count;
void app_main(void){}
int main(void){
 assert(portable_catalog_count==20);
 bool waterfall=false,touchpad=false,buttons=false;
 for(unsigned selected=0;selected<portable_catalog_count;++selected){
  launched[0]=0;assert(app_module_init()==0);
  const t5_app_api_v1 *api=t5_app_get_api(1);assert(api);
  assert(api->installed_apps_refresh() && api->installed_apps_count()==20);
  for(unsigned i=0;i<portable_catalog_count;++i){
   t5_app_manifest_t item={0};assert(api->installed_apps_get(i,&item));
   assert(!strcmp(item.file_name,portable_catalog[i].file_name));
   assert(!strcmp(item.display_name,portable_catalog[i].display_name));
   assert(!strcmp(item.icon,portable_catalog[i].icon));
   assert(item.compatible);
   if(!strcmp(item.file_name,"waterfall.elf"))waterfall=true;
   if(!strcmp(item.file_name,"ble_touchpad.elf"))touchpad=true;
   if(!strcmp(item.file_name,"ble_buttons.elf"))buttons=true;
  }
  t5_app_manifest_t outside={0};assert(!api->installed_apps_get(20,&outside));
  assert(!api->request_app_launch(20) && !launched[0]);
  api->clear();api->fill_rect(0,0,240,240,true);
  assert(api->draw_icon(90,90,portable_catalog[selected].icon,36,false));api->present(false);
  assert(api->request_app_launch(selected));assert(!strcmp(launched,portable_catalog[selected].file_name));
  app_module_fini();assert(!frames&&!grants&&!subs);
 }
 assert(waterfall && touchpad && buttons);puts("Actual20-entry Watch catalog: refresh/count/get/icon/launch and bounds passed");
}
