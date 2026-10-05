/* Actual production RGB565 regression, not a mock text/font renderer.
 * The runner extracts a legacy fixture from the retained shipped atlases.
 * Link points_projection.c separately: its RTC header is a distinct ABI copy. */
#define WATCH_FACE_TEXT_TEST 1
#include "apps/clock/nova/nova.c"
#include "apps/clock/points_projection.h"
#include "points_label_legacy_fixture.inc"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

enum { FRAME_BYTES = 240 * 240 * 2 };
static uint8_t pixels[FRAME_BYTES], isolated[FRAME_BYTES], other[FRAME_BYTES];
static uint8_t guarded[240 * 488 + 32];
static bool auditing;
static unsigned current_face, current_scenario, label_calls, glyph_checks;
static unsigned full_drive_calls, first_drive_calls;
static unsigned target_calls[3][WATCH_FACE_COUNT];
static FILE *audit_log;

static unsigned ink(const uint8_t *p) {
    unsigned n=0;
    for(unsigned i=0;i<FRAME_BYTES;i+=2)n+=(p[i]|p[i+1])!=0;
    return n;
}
static void text_pixels(uint8_t *out,const face_font *font,const uint8_t *alpha,
                        const char *s,int x,int y,int spacing,int fit) {
    memset(out,0,FRAME_BYTES);
    canvas c={out,480};
    bool before=auditing;auditing=false;
    ftext_alpha(&c,font,s,x,y,spacing,fit,FWHITE,0,alpha);
    auditing=before;
}
static bool contains_target(const char *s,unsigned scenario) {
    return scenario==0?strstr(s,"Wakeup")!=NULL:
           scenario==1?strstr(s,"Drive")!=NULL:strstr(s,"WORK END")!=NULL;
}
/* Audit what the production renderer really sends to its text rasterizer.
 * Re-render that exact call independently, at its real native placement and
 * fit. This catches an empty/fully clipped label, not just a present glyph ID. */
static void face_text_test(const face_font *font,const char *s,int x,int y,
                           int spacing,int fit,const uint8_t *alpha) {
    if(!auditing||current_face<24)return;
    assert(strcmp(s,"END")&&strcmp(s,"BED"));
    bool visible=false;
    for(const char *p=s;*p;p++) {
        const face_glyph *g=fglyph(font,*p);
        if(!g){fprintf(stderr,"missing glyph %u, face %u, text %s\n",(unsigned char)*p,current_face,s);abort();}
        if(*p!=' ') {
            bool nonzero=false;
            for(unsigned j=0;j<(unsigned)g->width*g->height;j++)nonzero|=alpha[g->data+j]!=0;
            assert(nonzero);visible=true;
        }
    }
    text_pixels(isolated,font,alpha,s,x,y,spacing,fit);
    assert(!visible||ink(isolated)>0);
    if(contains_target(s,current_scenario))target_calls[current_scenario][current_face]++;
    /* A shortened custom label must end after its complete first word. */
    const char *drive=strstr(s,"Drive");
    if(drive) {
        const char *after=drive+5;
        assert(!strncmp(after," to Work",8)||!*after||!strncmp(after," IN",3)||
               (*after==' '&&after[1]>='0'&&after[1]<='9'));
        if(current_scenario==1) {
            if(!strncmp(after," to Work",8))full_drive_calls++;
            else first_drive_calls++;
        }
    }
    if(audit_log)fprintf(audit_log,"%u\t%u\t%d\t%d\t%d\t%d\t%u\t%s\n",
                         current_scenario,current_face,x,y,spacing,fit,ink(isolated),s);
    label_calls++;
}
static void save_frame(const char *directory,const char *name,const uint8_t *p) {
    char path[1024];assert(snprintf(path,sizeof(path),"%s/%s.rgb565",directory,name)>0);
    FILE *f=fopen(path,"wb");assert(f);
    assert(fwrite(p,1,FRAME_BYTES,f)==FRAME_BYTES);assert(!fclose(f));
}
typedef struct {const char *name;const face_font *font;const uint8_t *alpha;} style;
static const style styles[]={
    {"ff_r7",&ff_r7,face_alpha},{"ff_r9",&ff_r9,face_alpha},
    {"ff_r10",&ff_r10,face_alpha},{"ff_r11",&ff_r11,face_alpha},
    {"ff_r12",&ff_r12,face_alpha},{"ff_m10",&ff_m10,face_alpha},
    {"ff_m11",&ff_m11,face_alpha},{"ff_o14",&ff_o14,face_alpha},
    {"ps_r14",&ps_f_r14,points_alpha},{"ps_r15",&ps_f_r15,points_alpha},
    {"ps_o34",&ps_f_o34,points_alpha}
};
static void check_printable_pixels(const char *directory) {
    char path[1024];snprintf(path,sizeof(path),"%s/glyph-pixels.tsv",directory);
    FILE *f=fopen(path,"w");assert(f);fputs("style\tcodepoint\tnative_pixels\tfit_pixels\n",f);
    for(unsigned i=0;i<COUNT(styles);i++)for(unsigned code=32;code<=126;code++) {
        const style *t=styles+i;char s[]={(char)code,0};
        const face_glyph *g=fglyph(t->font,(char)code);
        if(!g){fprintf(stderr,"%s omits printable ASCII %u\n",t->name,code);abort();}
        assert(g->advance>0);
        text_pixels(pixels,t->font,t->alpha,s,120,120,0,0);
        unsigned native=ink(pixels);
        int fit=(int)(g->advance*7u/2560u);if(fit<1)fit=1;
        text_pixels(other,t->font,t->alpha,s,120,120,0,fit);
        unsigned fitted=ink(other);
        /* Space is intentionally blank, with positive advance. Every other
         * printable ASCII character must contribute actual RGB565 pixels. */
        assert(code==32?(native==0&&fitted==0):(native>0&&fitted>0));
        fprintf(f,"%s\t%u\t%u\t%u\n",t->name,code,native,fitted);glyph_checks++;
    }
    assert(!fclose(f));
}
static void check_legacy_failure(const char *directory) {
    text_pixels(pixels,&legacy_ps_r14,legacy_points_alpha,"Drive to Work",120,120,1024,0);
    text_pixels(other,&legacy_ps_r14,legacy_points_alpha,"D  W",120,120,1024,0);
    assert(ink(pixels)>0&&!memcmp(pixels,other,FRAME_BYTES));
    save_frame(directory,"legacy-drive-collapsed",pixels);
    text_pixels(other,&ps_f_r14,points_alpha,"Drive to Work",120,120,1024,0);
    assert(ink(other)>ink(pixels)&&memcmp(pixels,other,FRAME_BYTES));
    save_frame(directory,"current-drive-complete",other);
    text_pixels(pixels,&legacy_ff_r10,legacy_face_alpha,"Wakeup",120,120,512,0);
    text_pixels(other,&legacy_ff_r10,legacy_face_alpha,"W",120,120,512,0);
    assert(ink(pixels)>0&&!memcmp(pixels,other,FRAME_BYTES));
    save_frame(directory,"legacy-wakeup-collapsed",pixels);
    text_pixels(other,&ff_r10,face_alpha,"Wakeup",120,120,512,0);
    assert(ink(other)>ink(pixels)&&memcmp(pixels,other,FRAME_BYTES));
    save_frame(directory,"current-wakeup-complete",other);
    puts("Reproduced shipped pixels: Drive to Work == D  W; Wakeup == W. Current text differs and has complete glyph coverage.");
}
static void check_width_rule(void) {
    nova_point_event event={.kind=NOVA_POINT_CUSTOM_1,.hour=5,.minute=30,.source_slot=1,.color_index=6};
    memcpy(event.label,"Drive to Work",14);
    const nova_point_event before=event;
    char result[NOVA_POINT_LABEL_MAX+1];
    for(unsigned i=0;i<COUNT(styles);i++)for(int spacing=0;spacing<=1024;spacing+=256) {
        const face_font *font=styles[i].font;
        unsigned width=ps_text_width(font,event.label,spacing);assert(width>1);
        assert(!strcmp(ps_label(result,&event,false,font,spacing,(int)width),"Drive to Work"));
        assert(!strcmp(ps_label(result,&event,false,font,spacing,(int)width+1),"Drive to Work"));
        assert(!strcmp(ps_label(result,&event,false,font,spacing,(int)width-1),"Drive"));
        /* Even an impossibly narrow slot retains a whole first word. The
         * existing raster fit can scale it; it must never become an initial. */
        assert(!strcmp(ps_label(result,&event,true,font,spacing,1),"Drive"));
        assert(!memcmp(&before,&event,sizeof(event)));
    }
    memcpy(event.label,"Wakeup",7);
    assert(!strcmp(ps_label(result,&event,true,&ff_r9,0,1),"Wakeup"));
    memcpy(event.label,"ZyX 9!?@~",10);
    assert(!strcmp(ps_label(result,&event,false,&ps_f_r14,256,240),"ZyX 9!?@~"));
    assert(!strcmp(ps_label(result,&event,false,&ps_f_r14,256,1),"ZyX"));
    event.is_end=true;
    assert(!strcmp(ps_label(result,&event,false,&ff_r9,0,240),"BACK"));
    event.is_end=false;event.kind=NOVA_POINT_WORK_END;
    assert(!strcmp(ps_label(result,&event,false,&ff_r9,0,240),"WORK END"));
    assert(!strcmp(ps_label(result,&event,true,&ff_r9,0,240),"WORK END"));
    assert(ps_text_width(&ff_r9,"WORK END",0)<=44);
    assert(!strcmp(ps_label(result,&event,true,&ff_r9,0,44),"WORK END"));
    event.kind=NOVA_POINT_BEDTIME;
    assert(!strcmp(ps_label(result,&event,true,&ff_r9,0,44),"BEDTIME"));
}
static void render_guarded(const nova_watch_state *s,unsigned face) {
    memset(guarded,0xa5,sizeof(guarded));
    risc_display_surface_v1 a={0,guarded+16,240,240,488,240*488,5};
    risc_display_surface_v1 b={0,pixels,240,240,480,sizeof(pixels),5};
    auditing=true;assert(nova_watch_face_render(&a,s,face));auditing=false;
    assert(nova_watch_face_render(&b,s,face));
    for(unsigned y=0;y<240;y++) {
        assert(!memcmp(guarded+16+y*488,pixels+y*480,480));
        for(unsigned x=480;x<488;x++)assert(guarded[16+y*488+x]==0xa5);
    }
    for(unsigned i=0;i<16;i++)assert(guarded[i]==0xa5&&guarded[sizeof(guarded)-1-i]==0xa5);
}
static void check_default_frames(const char *directory) {
    points_config config=points_default_config(),decoded_config;
    points_meta meta=points_default_meta(),decoded_meta;
    uint8_t config_bytes[POINTS_RECORD_SIZE],meta_bytes[POINTS_RECORD_SIZE];
    points_config_encode(&config,config_bytes);points_meta_encode(&meta,meta_bytes);
    assert(points_config_decode(&decoded_config,config_bytes,sizeof(config_bytes)));
    assert(points_meta_decode(&decoded_meta,meta_bytes,sizeof(meta_bytes)));
    assert(!strcmp(decoded_meta.custom[0].name,"Drive to Work"));
    assert(!strcmp(decoded_meta.custom[1].name,"Wakeup"));
    const unsigned hours[]={4,4,16},minutes[]={0,45,15};
    for(unsigned scenario=0;scenario<3;scenario++) {
        current_scenario=scenario;
        uint32_t midnight;assert(alarm_calendar_seconds(2026,10,5,0,0,0,&midnight));
        /* Production target stores UTC+8 RTC and displays America/Denver.
         * On October 5 the raw RTC is fourteen hours ahead of civil time. */
        uint32_t raw=midnight+(hours[scenario]+14)*3600+minutes[scenario]*60;
        nova_points_state projection;
        assert(watch_points_projection(&decoded_config,&decoded_meta,raw,&projection));
        assert(projection.status==NOVA_POINTS_READY&&projection.today_count==11&&projection.work_valid);
        assert(projection.next_count&&projection.next[0].kind==
               (scenario==0?NOVA_POINT_CUSTOM_2:scenario==1?NOVA_POINT_CUSTOM_1:NOVA_POINT_WORK_END));
        if(scenario<2)assert(!strcmp(projection.next[0].label,scenario?"Drive to Work":"Wakeup"));
        nova_watch_state state={.time={2026,10,5,1,(uint8_t)hours[scenario],(uint8_t)minutes[scenario],0},
            .time_valid=true,.battery_valid=true,.battery_percent=84,.subsecond_ms=250,.animation_ms=42000,.points=&projection};
        nova_points_state before=projection;
        for(unsigned face=0;face<WATCH_FACE_COUNT;face++) {
            current_face=face;render_guarded(&state,face);
            assert(!memcmp(&before,&projection,sizeof(before)));
            char name[80];snprintf(name,sizeof(name),"default-%u-face-%02u",scenario,face);
            save_frame(directory,name,pixels);
            /* All schedule designs other than the dedicated work-progress
             * face must really rasterize the selected next event's name. */
            if(face>=24&&face!=31) {
                if(!target_calls[scenario][face])fprintf(stderr,"No target label: scenario %u, face %u\n",scenario,face);
                assert(target_calls[scenario][face]>0);
            }
            if(face<24)assert(target_calls[scenario][face]==0);
        }
    }
    uint8_t after[POINTS_RECORD_SIZE];points_meta_encode(&decoded_meta,after);
    assert(!memcmp(after,meta_bytes,sizeof(after)));
    points_config_encode(&decoded_config,after);assert(!memcmp(after,config_bytes,sizeof(after)));
    assert(full_drive_calls>0&&first_drive_calls>0);
}
int main(int argc,char **argv) {
    assert(argc==2&&WATCH_FACE_COUNT==33);
    char path[1024];snprintf(path,sizeof(path),"%s/text-calls.tsv",argv[1]);
    audit_log=fopen(path,"w");assert(audit_log);
    fputs("scenario\tface\tx\ty\tspacing\tfit\tink_pixels\ttext\n",audit_log);
    check_printable_pixels(argv[1]);check_legacy_failure(argv[1]);check_width_rule();
    check_default_frames(argv[1]);
    assert(!fclose(audit_log));
    printf("Points labels: %u printable glyphs in 11 styles rendered at native/fitted widths; %u schedule text calls; 3 real default projections x 33 guarded 240x240 faces passed.\n",glyph_checks,label_calls);
    return 0;
}
