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
    face.contexts=v;
}
static bool clock_contexts_tick(void) {
    if(clock_contexts_uncertain||held||!clock_display_settled)return false;
    if(clock_alarm_modal||picker.open||pqa_visible(&clock_quick.ui)||pqa_capture(&clock_quick.ui)) {
        if(!clock_contexts_pause())return false;
    } else if(!portable_contexts_step(&clock_contexts,true,true))return clock_contexts_failure();
    contexts_status_v1 s={.struct_size=sizeof(s)};
    if(!clock_contexts.api->status(clock_contexts.api->context,&s))return clock_contexts_failure();
    if(clock_contexts.settings_valid&&clock_contexts.policy.enabled&&!s.export_active&&!s.export_pending) {
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
