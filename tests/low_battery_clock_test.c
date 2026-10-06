#define main original_quick_clock_main
#include "quick_clock_test.c"
#undef main
static void check(unsigned percent,unsigned flags){clock_ms+=5001;low_percent=percent;low_flags=flags;assert(clock_low_battery_poll(clock_ms));assert(grants==ungrants);}
int main(void){
 scenario=8;rt=&runtime;display=&da.base;panel=&da;pmu=&pa;rtc=&ra;submitted=1;last_complete=1;
 pqa_session_init(&clock_quick);assert(pqa_session_load(&clock_quick,rt));
 assert(pqa_radios_load(&clock_radios,&clock_quick.ui,rt));
 check(10,0);assert(!low_writes[0]);check(9,0);
 assert(clock_quick.brightness==15&&hardware_brightness==15&&clock_brightness()==15);
 assert(clock_quick.idle_ms==20000&&clock_quick.deep_ms==60000&&!clock_quick.ui.wifi_enabled&&!ble_state);
 clock_quick.ui.action_brightness=80;bool changed=false;
 assert(pqa_session_apply(&clock_quick,rt,display,PQA_BRIGHTNESS_COMMIT,&changed));
 assert(pqa_radios_apply(&clock_radios,&clock_quick.ui,rt,PQA_WIFI));
 assert(pqa_radios_apply(&clock_radios,&clock_quick.ui,rt,PQA_BLUETOOTH));
 assert(portable_sleep_timer_save(&face_kv,false,120000)&&portable_sleep_timer_save(&face_kv,true,600000));
 assert(pqa_session_load(&clock_quick,rt));check(8,0);check(7,RISC_BATTERY_CHARGING);
 assert(clock_quick.brightness==80&&hardware_brightness==80&&clock_quick.idle_ms==120000&&clock_quick.deep_ms==600000&&ble_state);
 clock_low_battery=(portable_low_battery){0};pqa_session_init(&clock_quick);assert(pqa_session_load(&clock_quick,rt));
 check(1,0);assert(clock_quick.brightness==80&&low_writes[0]==1);
 check(255,0);check(100,RISC_BATTERY_PROFILE_MISSING);check(100,PORTABLE_POWER_STATUS_VALID);check(9,0);assert(low_writes[0]==1);
 check(10,0);check(9,0);assert(low_writes[0]==3&&clock_quick.deep_ms==60000&&clock_quick.brightness==15&&!ble_state);
 /* Real Clock sleep consumes the same confirmed timer, not the old 5 minutes. */
 clock_ms=2000;sleep_mode=PORTABLE_SLEEP_HYBRID;assert(sleep_cycle()==1);assert(watch_sleep_light_ms==60000&&sleeps==1);
 assert(grants==ungrants);
 puts("Low-battery real Clock: crossings, manual controls, reboot, unknown/charging and configured sleep timer passed");
}
