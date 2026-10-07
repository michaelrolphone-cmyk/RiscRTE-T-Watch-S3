/* Exercise the accepted alarm-resume sequence with the new variable timer. */
#define ALARM_RESUME_FIXTURE_MAIN original_resume_main
#include "alarm_resume_client_test.c"
int main(void){
 for(unsigned seconds=30;seconds<=61;seconds++){
  current_reset();watch_sleep_light_ms=60000;entry_result=0;deadline=1000+seconds;
  int result=current(PORTABLE_SLEEP_HYBRID);assert(resumes==1&&light_calls==1);
  if(seconds<=60){assert(result==WATCH_SLEEP_WOKE&&service_due&&!deep_calls&&duration_seen==seconds*1000u);}
  else {assert(result==WATCH_SLEEP_RETAINED&&deep_calls==1&&duration_seen==1000u&&!refreshes);}
 }
 current_reset();watch_sleep_light_ms=60000;entry_result=0;deadline=2000;
 assert(current(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_RETAINED&&now==1060&&duration_seen==940000&&resumes==1);
 current_reset();watch_sleep_light_ms=600000;entry_result=0;deadline=2000;
 assert(current(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_RETAINED&&now==1600&&duration_seen==400000&&resumes==1);
 current_reset();watch_sleep_light_ms=60000;entry_result=0;deadline=0;
 assert(current(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_RETAINED&&now==1060&&deep_calls==1&&!duration_seen&&resumes==1);
 current_reset();watch_sleep_light_ms=60000;entry_result=0;deadline=2000;crown=true;
 assert(current(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_WOKE&&!deep_calls&&resumes==1);
 current_reset();watch_sleep_light_ms=60000;entry_result=0;deadline=2000;resume_result=ALARM_RTC;
 assert(current(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_REFUSED&&!deep_calls&&resumes==1&&!refreshes);
 puts("Low battery Hybrid timer: exact one-minute transition, manual timer, earlier/equal/later alarm deadlines, crown and resume errors passed");return 0;
}
