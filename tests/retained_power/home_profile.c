/* Additive host fixture. All Home policy/scheduling remains in pinned source. */
#if !defined(PORTABLE_LOW_BATTERY) || !defined(WATCH_ATOMIC_PREFERENCES) || !defined(PORTABLE_QUICK_ATOMIC_PREFERENCES) || !defined(PORTABLE_PREFERENCE_STORE)
#error Exact selected Home timer and Runtime preference flags are required
#endif
#include "home_fixture.inc"

static uint8_t record_bytes[3][5];
static uint32_t record_sizes[3];
static unsigned record_reads[3],namespace_reads[7],prepares,resumes,light_requests,deep_requests,preference_reads;
static uint32_t wanted_idle,wanted_deep,arming_at,observed_idle_at;
static unsigned wanted_mode,fault,phase;
static bool armed,predeadline_seen,request_done;
static risc_key_value_v1 scoped_kv[7];
static risc_key_value_atomic_v1 scoped_preferences;
static int record_index(const char*k){return !strcmp(k,"sleep_mode")?0:!strcmp(k,"sleep_idle")?1:!strcmp(k,"sleep_deep")?2:-1;}
static int32_t scoped_get(void*c,const char*k,void*out,uint32_t cap,uint32_t*n){
 uintptr_t ns=(uintptr_t)c;assert(ns<7);namespace_reads[ns]++;
 int ix=record_index(k);
 if(ix<0)return fast_get(NULL,k,out,cap,n);
 *n=0;assert(ns==1);record_reads[ix]++;
 if(fault==1 || ns!=(fault==3?2u:1u))return RISC_KEY_VALUE_NOT_FOUND; /* Missing or actually stored in private namespace2. */
 if(fault==4)return RISC_KEY_VALUE_IO;
 *n=record_sizes[ix];if(cap<*n)return RISC_KEY_VALUE_BUFFER_SMALL;
 memcpy(out,record_bytes[ix],*n);if(fault==2)((uint8_t*)out)[*n-1]^=0x80;
 return RISC_KEY_VALUE_OK;
}
static int32_t scoped_atomic_get(void*c,uint64_t revision,const char*k,void*out,uint32_t cap,uint32_t*n){
 assert((uintptr_t)c==1);preference_reads++;if(revision!=atomic_revision)return RISC_ATOMIC_STALE;
 int rc=scoped_get(c,k,out,cap,n);
 return rc==RISC_KEY_VALUE_OK?RISC_ATOMIC_OK:rc==RISC_KEY_VALUE_NOT_FOUND?RISC_ATOMIC_NOT_FOUND:RISC_ATOMIC_IO;
}
static bool profile_acquire(const char*n,uint32_t version,uint64_t instance,risc_runtime_capability_v1*g){
 if(!strcmp(n,RISC_KEY_VALUE_CAPABILITY)){
  assert(version==1&&(instance==1||instance==3||instance==5||instance==6));
  if(instance==1&&fault==5)return false;
  bool ok=fast_acquire(n,version,instance,g);
  if(ok){scoped_kv[instance]=fast_kv;scoped_kv[instance].context=(void*)(uintptr_t)instance;scoped_kv[instance].get=scoped_get;g->api=&scoped_kv[instance];}
  return ok;
 }
 bool ok=fast_acquire(n,version,instance,g);
 if(ok&&!strcmp(n,RISC_PREFERENCE_STORE_CAPABILITY)){
  assert(version==1&&instance==1);scoped_preferences=*(const risc_key_value_atomic_v1*)g->api;
  scoped_preferences.context=(void*)(uintptr_t)1;scoped_preferences.get=scoped_atomic_get;g->api=&scoped_preferences;
 }
 return ok;
}
static bool profile_health(risc_runtime_health_v1*h){
 check_io();
 if(armed&&clock_deferred_phase==4&&!request_done){
  if(!phase){clock_ms=arming_at+wanted_idle-1;phase=1;}
  else if(predeadline_seen){if(clock_ms<arming_at+wanted_idle)clock_ms=arming_at+wanted_idle;phase=2;}
 }
 h->uptime_ms=clock_ms;return !request_done&&clock_ms<arming_at+wanted_idle+10000u;
}
static bool profile_key(void*c,uint32_t*out){
 (void)c;check_io();*out=0;
 if(phase==1){assert(clock_ms>=arming_at+wanted_idle-1);assert(!light_requests&&!deep_requests);predeadline_seen=true;}
 return true;
}
static bool profile_diagnostic(const char*s){
 if(!strcmp(s,"WATCH_KEY arming=start interval-ms=250")){armed=true;arming_at=clock_ms;}
 if(!strcmp(s,"WATCH_KEY sleep-enter=idle")){observed_idle_at=clock_ms;assert(predeadline_seen&&clock_ms>=arming_at+wanted_idle);}
 if(!strncmp(s,"WATCH_SLEEP error=",18)){
  assert(fault==5&&!strcmp(s,"WATCH_SLEEP error=settings-acquire capability=storage.key-value instance=1"));
  sleep_acquire_errors++;return true;
 }
 if(!strncmp(s,"WATCH_CLOCK sleep=refused",25)){
  if(fault==5){
   assert(!strcmp(s,"WATCH_CLOCK sleep=refused stage=SETTINGS detail=unavailable"));
   assert(prepares==1&&resumes==1&&!light_requests&&!deep_requests);request_done=true;
  }else{
   char expected[80];snprintf(expected,sizeof(expected),"WATCH_CLOCK sleep=refused stage=DEEP detail=%d",RISC_DEEP_SLEEP_PLATFORM);
   if(!(request_done&&deep_requests==1&&!strcmp(s,expected)))fprintf(stderr,"refusal=%s expected=%s done=%d deep=%u light=%u\n",s,expected,request_done,deep_requests,light_requests);
   assert(request_done&&deep_requests==1&&!strcmp(s,expected));
  }
  return true; /* These modeled refusals are outside the inherited fixture's acquisition-only assertion. */
 }
 return fast_diagnostic(s);
}
static int32_t profile_begin(uint64_t*token){assert(!owned&&!pending&&!touch.subscription);prepares++;*token=77;return RISC_RUNTIME_SLEEP_OK;}
static int32_t profile_end(uint64_t token){assert(token==77);resumes++;return RISC_RUNTIME_SLEEP_OK;}
static int32_t profile_light(void*c,uint32_t ms,risc_light_sleep_result_v1*out){
 (void)c;check_io();assert(observed_idle_at&&watch_sleep_light_ms==wanted_deep);
 assert(ms==(wanted_mode==PORTABLE_SLEEP_HYBRID?wanted_deep:0));light_requests++;
 out->wake_cause=RISC_LIGHT_SLEEP_WAKE_TIMER;
 if(wanted_mode==PORTABLE_SLEEP_LIGHT)request_done=true;
 return RISC_LIGHT_SLEEP_OK;
}
static int32_t profile_light_plain(void*c,risc_light_sleep_result_v1*out){return profile_light(c,0,out);}
static int32_t profile_deep(void*c,uint32_t ms){
 (void)c;check_io();assert(ms==0&&observed_idle_at&&watch_sleep_light_ms==wanted_deep);deep_requests++;request_done=true;
 return RISC_DEEP_SLEEP_PLATFORM; /* Observe request, then modeled refusal/cleanup, never terminal target entry. */
}
static int32_t profile_deep_plain(void*c){return profile_deep(c,0);}
static int32_t profile_panel_deep(void*c){(void)c;return 0;}
static int32_t profile_panel_resume(void*c){return da.resume(c)?0:RISC_DEEP_SLEEP_PLATFORM;}
static void parse_record(unsigned ix,const char*s){
 size_t n=strlen(s);assert(n==2*(ix?5:4));record_sizes[ix]=(uint32_t)(n/2);
 for(unsigned j=0;j<n/2;j++){unsigned value;assert(sscanf(s+2*j,"%2x",&value)==1);record_bytes[ix][j]=(uint8_t)value;}
}
int main(int argc,char**argv){
 assert(argc==8);for(unsigned i=0;i<3;i++)parse_record(i,argv[i+1]);
 wanted_mode=(unsigned)strtoul(argv[4],NULL,10);wanted_idle=(uint32_t)strtoul(argv[5],NULL,10);wanted_deep=(uint32_t)strtoul(argv[6],NULL,10);fault=(unsigned)strtoul(argv[7],NULL,10);
 reset_case();preference_flags=RISC_PREFERENCE_STORE_COPIED_INPUT;requested_wakes=0;fake_service_cost=service_start_cost=0;transfer_cost=1;light_wake_drift=0;
 fast_runtime.struct_size=sizeof(fast_runtime);fast_runtime.acquire=profile_acquire;fast_runtime.health=profile_health;fast_runtime.diagnostic=profile_diagnostic;
 fast_runtime.sleep_prepare=profile_begin;fast_runtime.sleep_resume=profile_end;
 pa.key_events=profile_key;pa.light_sleep=profile_light_plain;pa.light_sleep_for=profile_light;pa.light_sleep_set=profile_light;
 pa.deep_sleep=profile_deep_plain;pa.deep_sleep_for=profile_deep;pa.deep_sleep_set=profile_deep;da.prepare_deep_sleep=profile_panel_deep;da.base.struct_size=sizeof(da);da.resume_status=profile_panel_resume;
 app_main();
 assert(armed&&request_done&&observed_idle_at&&prepares==1&&resumes==prepares);
 assert(sleep_mode==wanted_mode&&clock_quick.idle_ms==wanted_idle&&clock_quick.deep_ms==wanted_deep);
 assert(light_requests==(unsigned)(fault!=5&&wanted_mode!=PORTABLE_SLEEP_DEEP));
 assert(deep_requests==(unsigned)(fault!=5&&wanted_mode!=PORTABLE_SLEEP_LIGHT));
 assert(generic_acquires>0&&preference_reads>0&&atomic_acquires==0&&namespace_reads[2]==0);
 assert(!atomic_count&&!atomic_token); /* Runtime preference read lifecycle, not an atomic write/durability claim. */
 if(fault!=5)assert(record_reads[0]&&record_reads[1]&&record_reads[2]&&namespace_reads[1]);
 else assert(!record_reads[0]&&!record_reads[1]&&!record_reads[2]);
 assert(!low_writes[1]&&!low_writes[2]);
 assert(!owned&&!pending&&!held&&!touch.subscription&&!allocations);
 assert(grants==ungrants&&subscribed==unsubscribed);
 assert(motion_prepares==(unsigned)(fault!=5)&&motion_resumes==motion_prepares&&alarm_resumes==(unsigned)(fault!=5&&wanted_mode!=PORTABLE_SLEEP_DEEP));
 printf("mode=%u idle_ms=%u deep_ms=%u fault=%u arm=%u idle_observed=%u light=%u deep=%u namespace1_reads=%u preference_acquires=%u PASS\n",wanted_mode,wanted_idle,wanted_deep,fault,arming_at,observed_idle_at,light_requests,deep_requests,namespace_reads[1],generic_acquires);
 return 0;
}
