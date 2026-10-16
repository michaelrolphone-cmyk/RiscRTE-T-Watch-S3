#include "PortableContextActions.h"
static uint32_t clock_context_checked;
static bool clock_context_rules(void){
 const contexts_fingerprint_service_v1*fp=contexts_fingerprint_api(clock_contexts.api);if(!fp)return true;
 uint32_t now=face.animation_ms;if(clock_context_checked&&(uint32_t)(now-clock_context_checked)<500u)return true;clock_context_checked=now;
 contexts_evaluate_v1 q={.struct_size=sizeof(q)};q.observation.enabled=clock_contexts.settings_valid&&clock_contexts.policy.enabled;
 q.observation.time_valid=face.time_valid;q.observation.hour=face.time.hour;
 risc_battery_sample_v1 battery={0};if(pmu&&pmu->base.read&&pmu->base.read(pmu->base.context,&battery)&&battery.percent<=100&&!(battery.flags&RISC_BATTERY_PROFILE_MISSING)){q.observation.battery_valid=true;q.observation.battery=battery.percent;q.observation.charging=!!(battery.flags&RISC_BATTERY_CHARGING);}
 if(!fp->fingerprint(fp->base.context,CONTEXTS_FP_EVALUATE,&q))return false;
 if(q.result.changed){
  if(!clock_background_pause())return false;
  risc_runtime_capability_v1 g={.struct_size=sizeof(g)};bool opened=rt->acquire(RISC_KEY_VALUE_CAPABILITY,1,1,&g);uint16_t success=0;
  for(unsigned f=0;f<CR_SETTINGS;f++)if(q.result.changed&(1u<<f))if(opened&&portable_context_setting(g.api,f,q.result.settings[f],clock_contexts.low_battery,watch_face_save))success|=1u<<f;
  if(g.api&&!rt->release(&g))return false;
  for(unsigned i=0;i<CR_RULES;i++){bool changed=false,complete=true;for(unsigned f=0;f<CR_SETTINGS;f++)if(q.result.winners[f]==(int)i&&(q.result.changed&(1u<<f))){changed=true;complete&=!!(success&(1u<<f));}if(changed){contexts_workflow_v1 report={.struct_size=sizeof(report),.rule=i,.result=complete?CR_APPLIED:CR_PARTIAL};if(!fp->fingerprint(fp->base.context,CONTEXTS_FP_WORKFLOW,&report))return false;}}
  if(opened){if(!pqa_session_load(&clock_quick,rt)||!pqa_session_restore(&clock_quick,display)||!pqa_radios_resume(&clock_radios,&clock_quick.ui,rt))return false;
   g=(risc_runtime_capability_v1){.struct_size=sizeof(g)};if(!rt->acquire(RISC_KEY_VALUE_CAPABILITY,1,1,&g))return false;unsigned selected=picker.selected;(void)portable_sleep_load(g.api,&sleep_mode);if(watch_face_load(g.api,&selected)==RISC_KEY_VALUE_OK)picker.selected=(uint8_t)selected;if(!rt->release(&g))return false;
  }
  if(clock_alarm.api)(void)clock_alarm.api->refresh(clock_alarm.api->context);
 }
 if(clock_context_message[0])return true;
 contexts_workflow_v1 action={.struct_size=sizeof(action),.claim=true};if(!fp->fingerprint(fp->base.context,CONTEXTS_FP_WORKFLOW,&action))return false;
 if(action.available){
  if(!clock_background_pause())return false;
  bool ok=false;
  if(action.step.kind==CR_MESSAGE){memcpy(clock_context_message,action.step.text,33);ok=true;}
  else if(action.step.kind==CR_TIMER){risc_runtime_capability_v1 g={0};ok=portable_context_timer(rt,clock_alarm.api,action.step.value,&g);if(g.api)return false;}
  else if(action.step.kind==CR_LAUNCH){ok=rt->request_launch(action.step.text);if(ok)clock_contexts_handoff=true;}
  action.claim=false;action.result=ok?CR_RAN:CR_FAILED;if(!fp->fingerprint(fp->base.context,CONTEXTS_FP_WORKFLOW,&action))return false;
 }
 return true;
}
/* Copied service observations only. Source apps retain model storage ownership;
 * ordinary app handoff performs one bounded export at a time. */
static bool clock_contexts_failure(void) {
    clock_contexts_uncertain=true;
#ifdef WATCH_RUNTIME_FEATURES
    watch_runtime_retain(rt);
#endif
    return false;
}
static bool clock_contexts_recover_export(void) {
    contexts_status_v1 s={.struct_size=sizeof(s)};
    if(!clock_contexts.api->status(clock_contexts.api->context,&s))return clock_contexts_failure();
    /* Successful owners clear active before return. Failed owner launch/init
     * becomes visible failure instead of an automatic launch loop. */
    if(s.export_active&&!clock_contexts.api->finish_export(clock_contexts.api->context,
        s.export_active,CONTEXTS_EXPORT_UNSUPPORTED))return clock_contexts_failure();
    return true;
}
static void clock_contexts_project(const contexts_status_v1 *s) {
    nova_context_state v={0};v.enabled=clock_contexts.settings_valid&&clock_contexts.policy.enabled;
    v.ready=s->audio.model_state==CONTEXTS_MODEL_READY||s->radio.model_state==CONTEXTS_MODEL_READY;
    v.paused=s->state!=CONTEXTS_LIVE;v.ambiguous=s->audio.room_ambiguous||s->radio.room_ambiguous;
    const contexts_source_status_v1 *room=NULL,*event=NULL;
    if(s->audio.current&&s->audio.room_valid&&!s->audio.room_ambiguous)room=&s->audio;
    if(s->radio.current&&s->radio.room_valid&&!s->radio.room_ambiguous) {
        if(room&&strncmp(room->room_name,s->radio.room_name,17)){room=NULL;v.ambiguous=true;}
        else if(!room)room=&s->radio;
    }
    if(room&&memchr(room->room_name,0,17)&&!v.ambiguous) {
        memcpy(v.room,room->room_name,17);v.source=(uint8_t)room->source;v.room_valid=true;
    }
    if(s->audio.current&&s->audio.event_valid&&!s->audio.event_ambiguous)event=&s->audio;
    else if(s->radio.current&&s->radio.event_valid&&!s->radio.event_ambiguous)event=&s->radio;
    if(event&&memchr(event->event_name,0,17)){memcpy(v.event,event->event_name,17);v.event_valid=true;}
    const contexts_fingerprint_service_v1*fp=contexts_fingerprint_api(clock_contexts.api);
    if(fp){contexts_fingerprint_status_v1 q={.struct_size=sizeof(q)};if(fp->fingerprint(fp->base.context,CONTEXTS_FP_STATUS,&q)){v.ready=q.generation!=0;v.room_valid=q.room_slot>=0;v.event_valid=q.event_slot>=0;v.ambiguous=q.room_ambiguous;memcpy(v.room,q.room_name,17);memcpy(v.event,q.event_name,17);}}
    face.contexts=v;
}
static bool clock_contexts_tick(void) {
    if(clock_contexts_uncertain||held||!clock_display_settled)return false;
    if(clock_alarm_modal||picker.open||pqa_visible(&clock_quick.ui)||pqa_capture(&clock_quick.ui)) {
        if(!clock_contexts_pause())return false;
    } else if(!portable_contexts_step(&clock_contexts,true,true))return clock_contexts_failure();
    contexts_status_v1 s={.struct_size=sizeof(s)};
    if(!clock_contexts.api->status(clock_contexts.api->context,&s))return clock_contexts_failure();
    if(!contexts_fingerprint_api(clock_contexts.api)&&clock_contexts.settings_valid&&clock_contexts.policy.enabled&&!s.export_active&&!s.export_pending) {
        uint32_t needed=(s.audio.model_state==CONTEXTS_MODEL_EMPTY?CONTEXTS_AUDIO:0u)|
            (s.radio.model_state==CONTEXTS_MODEL_EMPTY?CONTEXTS_RADIO:0u);
        if(needed) {
            if(!clock_background_pause()||!clock_contexts.api->request_export(clock_contexts.api->context,needed)||
               !clock_contexts.api->status(clock_contexts.api->context,&s))return clock_contexts_failure();
        }
    }
    clock_contexts_project(&s);
    if(s.export_pending&&!s.export_active&&!clock_alarm_modal&&!picker.open&&!pqa_visible(&clock_quick.ui)) {
        unsigned source=s.export_pending&CONTEXTS_AUDIO?CONTEXTS_AUDIO:CONTEXTS_RADIO;
        if(!clock_background_pause()||!clock_contexts.api->begin_export(clock_contexts.api->context,source))return clock_contexts_failure();
        if(rt->request_launch(source==CONTEXTS_AUDIO?"audio_spectrum.elf":"waterfall.elf")) {
            clock_contexts_handoff=true;
#ifdef WATCH_BLE_BROADCAST
            clock_handoff=true;
#endif
            return true;
        }
        return clock_contexts.api->finish_export(clock_contexts.api->context,source,CONTEXTS_EXPORT_UNSUPPORTED);
    }
    if(clock_alarm_modal||picker.open||pqa_visible(&clock_quick.ui)||pqa_capture(&clock_quick.ui))return true;
    if(clock_contexts.rules_available)return clock_context_rules();
    uint16_t applied=0;
    if(!portable_contexts_apply_room(&clock_contexts,&applied,watch_face_save))return clock_contexts_failure();
    if(applied) {
        if(!pqa_session_load(&clock_quick,rt)||!pqa_session_restore(&clock_quick,display))return false;
        if(applied&(PORTABLE_CONTEXT_VOLUME|PORTABLE_CONTEXT_DND|PORTABLE_CONTEXT_ALERT))
            (void)clock_alarm.api->refresh(clock_alarm.api->context);
        if(applied&(PORTABLE_CONTEXT_SLEEP|PORTABLE_CONTEXT_FACE)) {
            risc_runtime_capability_v1 g={.struct_size=sizeof(g)};
            if(!rt->acquire(RISC_KEY_VALUE_CAPABILITY,1,1,&g))return false;
            if(applied&PORTABLE_CONTEXT_SLEEP)(void)portable_sleep_load(g.api,&sleep_mode);
            if(applied&PORTABLE_CONTEXT_FACE){unsigned selected=picker.selected;if(watch_face_load(g.api,&selected)==RISC_KEY_VALUE_OK)picker.selected=(uint8_t)selected;}
            if(!rt->release(&g))return clock_contexts_failure();
        }
    }
    return true;
}
