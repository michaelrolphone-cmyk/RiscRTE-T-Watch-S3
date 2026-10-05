/* Points in Time: integer RGB565 adaptation of the owner's eight layouts.
 * Render only the caller's bounded snapshot. No calendar service, fabricated
 * meeting, local/absolute time conversion, storage access or allocation. */
#ifdef WATCH_POINTS_LEGACY_PRESENTATION
#include "points_assets.inc"
#else
#include "points_text_assets.inc"
#endif
#define PS_TEXT(c,font,s,x,y,spacing,fit,color) ftext_alpha(c,&ps_f_##font,s,x,y,spacing,fit,color,0,points_alpha)
#define PS_CAL(c,font,s,x,y,spacing,fit,color) ftext_alpha(c,&fc_f_##font,s,x,y,spacing,fit,color,0,calendar_alpha)
#define PS_CAP FC(107,130,136)
#define PS_PALE FC(207,233,238)
#define PS_BLUE FC(61,155,255)
#define PS_PINK FC(255,61,113)
#define PS_BED FC(109,123,255)
#define PS_BG FC(20,25,28)
static const uint16_t ps_custom_colors[8]={FC(255,210,74),FC(255,122,26),FC(255,61,113),FC(178,77,255),FC(109,123,255),FC(61,155,255),FC(25,227,255),FC(61,255,154)};
static bool ps_custom_kind(unsigned kind){return kind==NOVA_POINT_CUSTOM_1||kind==NOVA_POINT_CUSTOM_2;}
static bool ps_duration_kind(unsigned kind){return kind==NOVA_POINT_LUNCH||kind==NOVA_POINT_BREAK||ps_custom_kind(kind);}
static bool ps_custom_label_valid(const nova_point_event*e){
    if(!ps_custom_kind(e->kind))return true;
    if(e->color_index>=8||!e->label[0])return false;
    for(unsigned i=0;i<=NOVA_POINT_LABEL_MAX;i++)if(!e->label[i])return true;
    return false;
}
static unsigned ps_length(const char*s){unsigned n=0;while(n<64&&s[n])n++;return n;}
static int ps_fit(const face_font*font,const char*s,int spacing,int maximum) {
    unsigned width=0;for(const char*p=s;*p;p++){const face_glyph*g=fglyph(font,*p);if(g)width+=g->advance+(unsigned)spacing;}
    if(width)width-=(unsigned)spacing;
    return width>(unsigned)maximum*256u?maximum:0;
}
static bool ps_event_valid(const nova_point_event*e) {
    return e->hour<24&&e->minute<60&&e->source_slot<8&&e->kind>=NOVA_POINT_WORK_START&&e->kind<=NOVA_POINT_CUSTOM_2&&
        (!e->is_end||ps_duration_kind(e->kind))&&ps_custom_label_valid(e);
}
static const char*ps_event_name(const nova_point_event*e,bool brief) {
    if(!ps_event_valid(e))return "POINT ERROR";
    if(e->is_end)return "BACK";
    if(ps_custom_kind(e->kind))return e->label;
    switch(e->kind) {
#ifdef WATCH_POINTS_LEGACY_PRESENTATION
        case NOVA_POINT_WORK_START:return brief?"START":"WORK START";
#else
        case NOVA_POINT_WORK_START:return "WORK";
#endif
        case NOVA_POINT_WORK_END:return brief?"END":"WORK END";
        case NOVA_POINT_LUNCH:return "LUNCH";
        case NOVA_POINT_BREAK:return "BREAK";
        default:return brief?"BED":"BEDTIME";
    }
}
/* Fit by complete words, never by losing unsupported glyphs or initials.
 * The stored/projected label remains untouched; this buffer is frame-local. */
static unsigned ps_text_width(const face_font*font,const char*s,int spacing) {
    unsigned width=0;for(;*s;s++){const face_glyph*g=fglyph(font,*s);if(g)width+=g->advance+(unsigned)spacing;}
    if(width)width-=(unsigned)spacing;
    return (width+255u)/256u;
}
static const char*ps_label(char out[NOVA_POINT_LABEL_MAX+1],const nova_point_event*e,bool brief,
                          const face_font*font,int spacing,int maximum) {
    /* Current faces prefer complete built-in names too (WORK END, BEDTIME).
     * Historical abbreviations remain isolated in the legacy presentation. */
    (void)brief;const char*name=ps_event_name(e,false);unsigned n=0;
    while(n<NOVA_POINT_LABEL_MAX&&name[n]){out[n]=name[n];n++;}out[n]=0;
    if(ps_custom_kind(e->kind)&&ps_text_width(font,out,spacing)>(unsigned)(maximum>0?maximum:0)) {
        unsigned first=0;while(out[first]&&out[first]!=' ')first++;
        if(first&&out[first]==' ')out[first]=0;
    }
    return out;
}
static uint16_t ps_color(const nova_point_event*e) {
    if(ps_custom_kind(e->kind))return ps_custom_colors[e->color_index<8?e->color_index:6];
    if(e->is_end||e->kind==NOVA_POINT_WORK_START)return PS_BLUE;
    return e->kind==NOVA_POINT_WORK_END?PS_PINK:e->kind==NOVA_POINT_LUNCH?FAMBER:e->kind==NOVA_POINT_BREAK?FGREEN:PS_BED;
}
static const char*ps_phase_name(nova_points_phase p) {
    switch(p) {
        case NOVA_PHASE_WORKING:return "WORKING";
        case NOVA_PHASE_OFF_WORK:return "OFF WORK";
        case NOVA_PHASE_LUNCH:return "AT LUNCH";
        case NOVA_PHASE_BREAK:return "ON BREAK";
        case NOVA_PHASE_WIND_DOWN:return "WIND DOWN";
        default:return "NO PHASE";
    }
}
/* Countdown durations never wrap at midnight. uint32 max fits 1193046:28:15.
 * The compact mode preserves all elapsed hours rather than treating them as a
 * clock (e.g. 27:05 is twenty-seven hours, five minutes, never 03:05). */
static void ps_duration(char out[16],uint32_t seconds,bool compact) {
    unsigned h=seconds/3600,m=seconds/60%60,s=seconds%60,n=0;
    if(h||compact){fc_number(out,h);while(out[n])n++;out[n++]=':';two(out+n,m);n+=2;}
    else{two(out,m);n=2;}
    if(!compact){out[n++]=':';two(out+n,s);n+=2;}
    out[n]=0;
}
/* Local scheduled clock labels apply the same Settings policy as the current
 * clock. A day suffix prevents a future-weekday event looking like today. */
static void ps_relative(char out[24],uint32_t seconds) {
    unsigned minutes=seconds/60,h=minutes/60;
    if(!h){char number[12];fc_number(number,minutes);fc_join(out,24,number," MIN","");return;}
    fc_number(out,h);unsigned n=ps_length(out);out[n++]='H';out[n++]=' ';two(out+n,minutes%60);n+=2;out[n++]='M';out[n]=0;
}
static void ps_event_clock(char out[24],const nova_point_event*e,bool hour24,bool day) {
    if(!ps_event_valid(e)){memcpy(out,"--:--",6);return;}
    unsigned h=e->hour,n=5;if(!hour24){h%=12;if(!h)h=12;}
    two(out,h);out[2]=':';two(out+3,e->minute);
    if(!hour24){out[n++]=' ';out[n++]=e->hour<12?'A':'P';out[n++]='M';}
    if(day&&e->day_offset){out[n++]=' ';out[n++]=e->day_offset<0?'-':'+';unsigned d=e->day_offset<0?(unsigned)-(int)e->day_offset:(unsigned)e->day_offset;fc_number(out+n,d);while(out[n])n++;out[n++]='D';}
    out[n]=0;
}
/* Fixed-point fraction with no uint64 division dependency. Reduction bounds
 * both products even for malformed/full-range epoch intervals. */
static unsigned ps_fraction(uint32_t now,uint32_t start,uint32_t end) {
    if(end<=start||now<=start)return 0;
    if(now>=end)return 1024;
    uint32_t n=now-start,d=end-start;
    while(d>UINT32_MAX/1024u){d=(d>>1)+(d&1u);n>>=1;}
    return n*1024u/d;
}
static void ps_arc(canvas*c,int cx,int cy,int radius,unsigned fraction,int width,uint16_t color) {
    if(!fraction)return;
    if(fraction>1024)fraction=1024;
    int end=(int)(fraction*90u),px,py;fpoint(0,radius,cx,cy,&px,&py);
    for(int a=4*256;a<end+4*256;a+=4*256){int x,y;fpoint(a>end?end:a,radius,cx,cy,&x,&y);fline(c,px,py,x,y,width*16,color);px=x;py=y;}
}
static void ps_clock(canvas*c,const nova_watch_labels*l,int baseline,int size,uint16_t color) {
    if(size==42)PS_CAL(c,o42,l->hour_minute,120,baseline,0,124,color);
    else if(size==34)PS_CAL(c,o36,l->hour_minute,120,baseline,0,104,color);
    else if(size==30)PS_CAL(c,o28,l->hour_minute,120,baseline,0,94,color);
    else if(size==18)PS_TEXT(c,o18,l->hour_minute,120,baseline,256,0,color);
    else ftext(c,&ff_o14,l->hour_minute,120,baseline,768,0,color,0);
    if(l->time_valid&&l->meridiem[0])ftext(c,&ff_r9,l->meridiem,size>=30?192:183,baseline,0,0,PS_CAP,0);
}
static void ps_battery(canvas*c,const nova_watch_state*s,const nova_watch_labels*l,int y,uint16_t color) {
    fc_battery(c,s,l,120,y,7,color);
    /* Unknown telemetry is explicitly labeled, never an invented percentage. */
    if(!l->battery_valid)ftext(c,&ff_r9,"BATT --%",120,y+16,128,0,PS_CAP,0);
}
static const char*ps_problem(const nova_watch_state*s,const nova_watch_labels*l) {
    if(!l->time_valid)return "TIME UNSET";
    if(!s->points||s->points->status==NOVA_POINTS_UNAVAILABLE)return "UNAVAILABLE";
    const nova_points_state*p=s->points;
    if(p->status==NOVA_POINTS_EMPTY)return "NO POINTS";
    if(p->status!=NOVA_POINTS_READY||p->next_count>NOVA_POINTS_NEXT_MAX||p->today_count>NOVA_POINTS_TODAY_MAX)return "SCHEDULE ERROR";
    for(unsigned i=0;i<p->next_count;i++)if(!ps_event_valid(p->next+i)||p->next[i].at_rtc<p->now_rtc||p->next[i].day_offset<0||(i&&p->next[i].at_rtc<p->next[i-1].at_rtc))return "SCHEDULE ERROR";
    for(unsigned i=0;i<p->today_count;i++)if(!ps_event_valid(p->today+i)||p->today[i].day_offset||(i&&p->today[i].at_rtc<p->today[i-1].at_rtc))return "SCHEDULE ERROR";
    if(p->previous_valid&&(!ps_event_valid(&p->previous)||p->previous.at_rtc>p->now_rtc))return "SCHEDULE ERROR";
    if(p->phase>NOVA_PHASE_WIND_DOWN)return "SCHEDULE ERROR";
    return NULL;
}
static const nova_point_event*ps_matching_end(const nova_points_state*p,const nova_point_event*start) {
    if(!start||start->is_end||!ps_duration_kind(start->kind))return NULL;
    const nova_point_event*best=NULL;
    for(unsigned pass=0;pass<2;pass++) {
        const nova_point_event*events=pass?p->next:p->today;unsigned count=pass?p->next_count:p->today_count;
        for(unsigned i=0;i<count;i++) {
            const nova_point_event*e=events+i;
            if(!e->is_end||e->kind!=start->kind||e->source_slot!=start->source_slot||e->at_rtc<=start->at_rtc)continue;
            if(!best||e->at_rtc<best->at_rtc)best=e;
        }
    }
    return best;
}
static bool ps_active_interval(const nova_points_state*p,const nova_point_event**start,const nova_point_event**end) {
    const nova_point_event*a=NULL,*b=NULL;
    if(p->previous_valid&&!p->previous.is_end&&ps_duration_kind(p->previous.kind)) {
        b=ps_matching_end(p,&p->previous);
        if(b&&p->previous.at_rtc<=p->now_rtc&&p->now_rtc<b->at_rtc)a=&p->previous;
    }
    for(unsigned i=0;!a&&i<p->today_count;i++) {
        const nova_point_event*e=p->today+i;
        if(e->is_end||!ps_duration_kind(e->kind)||e->at_rtc>p->now_rtc)continue;
        const nova_point_event*q=ps_matching_end(p,e);
        if(q&&p->now_rtc<q->at_rtc){a=e;b=q;}
    }
    if(start)*start=a;
    if(end)*end=b;
    return a&&b;
}
static const nova_point_event*ps_upcoming_start(const nova_points_state*p,uint32_t after,bool strict) {
    for(unsigned i=0;i<p->next_count;i++) {
        const nova_point_event*e=p->next+i;
        if(e->is_end)continue;
        if(strict?e->at_rtc>after:e->at_rtc>=after)return e;
    }
    return NULL;
}
static int ps_clock_angle(const nova_point_event*e) {
    return (int)(((unsigned)(e->hour%12)*60u+e->minute)*128u);
}
static void ps_clock_arc(canvas*c,int radius,int from,int to,int width,uint16_t color) {
    const int full=360*256;
    while(from<0)from+=full;
    from%=full;
    while(to<=from)to+=full;
    if(to-from>full)to=from+full;
    int px,py;fpoint(from,radius,120,120,&px,&py);
    for(int a=from+2*256;a<to+2*256;a+=2*256) {
        int q=a>to?to:a,x,y;fpoint(q%full,radius,120,120,&x,&y);fline(c,px,py,x,y,width,color);px=x;py=y;
    }
}
static void ps_up_next_marker(canvas*c,const nova_points_state*p,const nova_point_event*e) {
    if(!e||e->is_end)return;
    const nova_point_event*end=ps_matching_end(p,e);
    bool active=end&&e->at_rtc<=p->now_rtc&&p->now_rtc<end->at_rtc;
    if(end) {
        if(end->at_rtc<=p->now_rtc)return;
        if(e->at_rtc>p->now_rtc&&e->at_rtc-p->now_rtc>43200u)return;
    } else {
        if(e->at_rtc<=p->now_rtc||e->at_rtc-p->now_rtc>43200u)return;
    }
    int angle=ps_clock_angle(e),x,y;uint16_t col=ps_color(e);
    if(end&&end->at_rtc>e->at_rtc)ps_clock_arc(c,88,angle,ps_clock_angle(end),active?80:48,col);
    fpoint(angle,88,120,120,&x,&y);fcirc(c,x,y,(active?5:4)*16,0,col);
}
static void ps_problem_face(canvas*c,const nova_watch_state*s,const nova_watch_labels*l,unsigned id,const char*problem) {
    if(id==1)fcirc(c,1920,1920,98*16,8*16,PS_BG);
    ps_clock(c,l,id==1?62:48,18,FWHITE);
    ftext(c,&ff_r11,id==7?"WORKDAY":"DAILY POINTS",120,91,640,0,PS_CAP,0);
    PS_TEXT(c,r15,problem,120,126,256,ps_fit(&ps_f_r15,problem,256,180),FORANGE);
    ftext(c,&ff_r10,!l->time_valid?"CHECK CLOCK SETTINGS":s->points&&s->points->status==NOVA_POINTS_EMPTY?"SET POINTS IN DAILY":"CHECK DAILY SETTINGS",120,151,256,0,PS_CAP,0);
    ps_battery(c,s,l,196,PS_CAP);
}
static void fpoints_collection(canvas*c,const nova_watch_state*s,const nova_watch_labels*l,unsigned id) {
    const char*problem=ps_problem(s,l);if(problem){ps_problem_face(c,s,l,id,problem);return;}
    const nova_points_state*p=s->points;
    const nova_point_event*nx=p->next_count?p->next:NULL;
    uint16_t color=nx?ps_color(nx):PS_CAP;
    uint32_t remain=nx?nx->at_rtc-p->now_rtc:0;
    unsigned progress=nx&&p->previous_valid?ps_fraction(p->now_rtc,p->previous.at_rtc,nx->at_rtc):0;
    char timer[16],clock[24],label[64],event_label[NOVA_POINT_LABEL_MAX+1];ps_duration(timer,remain,false);
    if(id==0) { /* NEXT */
        ps_clock(c,l,40,14,PS_CAP);
        PS_TEXT(c,r14,nx?ps_label(event_label,nx,false,&ps_f_r14,1024,196):"NO UPCOMING",120,76,1024,0,color);
        if(ps_length(timer)>5)PS_CAL(c,o40,nx?timer:"--:--",120,134,0,186,FWHITE);
        else PS_CAL(c,o52,nx?timer:"--:--",120,134,0,136,FWHITE);
        fc_round_rect(c,30*16,150*16,180*16,4*16,2*16,FC(26,32,36));
        if(nx&&p->previous_valid)fc_round_rect(c,30*16,150*16,(int)(180*16*progress/1024),4*16,2*16,color);
        if(p->previous_valid){ps_event_clock(clock,&p->previous,s->hour_24,false);ftext(c,&ff_r9,clock,62,172,0,0,PS_CAP,0);}
        if(nx){ps_event_clock(clock,nx,s->hour_24,true);ftext(c,&ff_r9,clock,179,172,0,0,color,0);}
        ps_battery(c,s,l,200,color);
    } else if(id==1) { /* RING */
        fcirc(c,1920,1920,98*16,8*16,PS_BG);
        if(nx&&p->previous_valid)ps_arc(c,120,120,98,1024-progress,8,color);
        PS_TEXT(c,r14,nx?ps_label(event_label,nx,false,&ps_f_r14,768,180):"NO UPCOMING",120,78,768,0,color);
        PS_CAL(c,o40,nx?timer:"--:--",120,126,0,ps_length(timer)>5?150:104,FWHITE);
        if(nx){ps_event_clock(clock,nx,s->hour_24,true);fc_join(label,sizeof(label),"AT ",clock,"");ftext(c,&ff_r10,label,120,146,384,0,FC(154,165,168),0);}
        ps_clock(c,l,166,14,PS_CAP);ps_battery(c,s,l,178,color);
    } else if(id==2) { /* LADDER */
        ps_clock(c,l,44,18,FWHITE);
        for(unsigned i=0;i<3;i++) {
            int y=84+(int)i*40;
            if(i>=p->next_count){ftext(c,&ff_r11,i?"--":"NO UPCOMING",120,y+5,256,0,PS_CAP,0);continue;}
            const nova_point_event*e=p->next+i;uint16_t col=ps_color(e);
            if(!i)fc_round_rect(c,22*16,(y-18)*16,196*16,36*16,10*16,fc_dim(col,46));
            frect(c,22,y-18,3,36,col);
            const char*name=ps_label(event_label,e,false,&ps_f_r15,256,84);
            PS_TEXT(c,r15,name,79,y+5,256,ps_fit(&ps_f_r15,name,256,84),i?FC(154,165,168):FWHITE);
            ps_event_clock(clock,e,s->hour_24,true);ftext(c,&ff_r11,clock,166,y-1,0,0,col,0);
            ps_relative(clock,e->at_rtc-p->now_rtc);fc_join(label,sizeof(label),"IN ",clock,"");ftext(c,&ff_r9,label,174,y+13,256,ps_fit(&ff_r9,label,256,82),PS_CAP,0);
        }
        ps_battery(c,s,l,204,FGREEN);
    } else if(id==3) { /* DAYLINE: full local day, never clamps early points. */
        ps_clock(c,l,58,42,FWHITE);
        ftext(c,&ff_r9,"TODAY",120,83,512,0,PS_CAP,0);
        frect(c,22,129,196,3,FC(26,32,36));
        unsigned wall=s->time.hour*3600u+s->time.minute*60u+s->time.second;
        int now_x=22+(int)(196u*wall/86400u);frect(c,22,129,now_x-22,3,PS_PALE);
        /* Preserve true tick positions. Alternate label rows and resolve
         * neighboring label collisions independently, keeping leaders short. */
        unsigned names[8],named=0;int label_x[8];
        for(unsigned i=0;i<p->today_count;i++)if(!p->today[i].is_end&&named<8){names[named]=i;label_x[named]=22+(int)(196u*(p->today[i].hour*60u+p->today[i].minute)/1440u);named++;}
        for(unsigned row=0;row<2;row++) {
            int previous=0;
            for(unsigned j=row;j<named;j+=2){if(label_x[j]<34)label_x[j]=34;if(previous&&label_x[j]<previous+48)label_x[j]=previous+48;previous=label_x[j];}
            int next=254;
            for(int j=(int)named-1;j>=0;j--)if((unsigned)j%2==row){if(label_x[j]>206)label_x[j]=206;if(label_x[j]>next-48)label_x[j]=next-48;next=label_x[j];}
        }
        for(unsigned i=0;i<p->today_count;i++) {
            const nova_point_event*e=p->today+i;int x=22+(int)(196u*(e->hour*60u+e->minute)/1440u);uint16_t col=ps_color(e);
            if(e->is_end){fline(c,x*16,126*16,x*16,134*16,16,fc_dim(col,128));continue;}
            unsigned j=0;while(j<named&&names[j]!=i)j++;unsigned row=j%2;
            fline(c,x*16,130*16,x*16,(row?143:117)*16,32,col);
            if(j<named){int lx=label_x[j];fline(c,x*16,(row?143:117)*16,lx*16,(row?152:110)*16,12,fc_dim(col,135));const char*name=ps_label(event_label,e,true,&ff_r9,0,44);ftext(c,&ff_r9,name,lx,row?163:105,0,ps_fit(&ff_r9,name,0,44),col,0);}
        }
        fcirc(c,now_x*16,130*16+8,5*16,0,FWHITE);
        if(!p->today_count)ftext(c,&ff_r11,"NO POINTS TODAY",120,109,512,0,PS_CAP,0);
        if(nx){ps_duration(timer,remain,false);char suffix[24];fc_join(suffix,sizeof(suffix)," IN ",timer,"");fc_join(label,sizeof(label),ps_label(event_label,nx,false,&ff_r11,384,190-(int)ps_text_width(&ff_r11,suffix,384)-2),suffix,"");}else memcpy(label,"NO UPCOMING",12);
        ftext(c,&ff_r11,label,120,188,384,ps_fit(&ff_r11,label,384,190),color,0);ps_battery(c,s,l,204,color);
    } else if(id==4) { /* TRIPLE */
        ps_clock(c,l,54,34,FWHITE);
        ftext(c,&ff_r9,"HOURS : MINUTES LEFT",120,79,256,0,PS_CAP,0);
        for(unsigned i=0;i<3;i++) {
            int x=52+(int)i*68;fcirc(c,x*16,122*16,26*16,5*16,PS_BG);
            if(i>=p->next_count){ftext(c,&ff_r11,"--",x,126,0,0,PS_CAP,0);continue;}
            const nova_point_event*e=p->next+i;uint32_t r=e->at_rtc-p->now_rtc;uint16_t col=ps_color(e);
            ps_arc(c,x,122,26,r>=14400?1024:r*1024u/14400u,5,col);
            ps_duration(timer,r,true);PS_CAL(c,o11,timer,x,126,0,ps_length(timer)>5?48:0,FWHITE);
            const char*name=ps_label(event_label,e,true,&ff_r9,128,58);
            ftext(c,&ff_r9,name,x,164,128,ps_fit(&ff_r9,name,128,58),col,0);
            ps_event_clock(clock,e,s->hour_24,false);ftext(c,&ff_r7,clock,x,178,0,0,PS_CAP,0);
        }
        if(!nx)ftext(c,&ff_r10,"NO UPCOMING",120,84,256,0,PS_CAP,0);
        ps_battery(c,s,l,200,FGREEN);
    } else if(id==5) { /* STATUS */
        uint16_t phase_color=p->previous_valid?ps_color(&p->previous):PS_CAP;
        ps_clock(c,l,44,14,PS_CAP);
        const char*phase=ps_phase_name(p->phase);PS_TEXT(c,o34,phase,120,98,0,(int)(ps_length(phase)*21u<196?ps_length(phase)*21u:196),phase_color);
        frect(c,50,112,140,3,FC(26,32,36));if(p->previous_valid&&nx)frect(c,50,112,(int)(140*progress/1024),3,phase_color);
        if(nx)fc_join(label,sizeof(label),ps_label(event_label,nx,false,&ff_r11,768,196-(int)ps_text_width(&ff_r11," IN",768)-3)," IN","");else memcpy(label,"NO UPCOMING",12);
        ftext(c,&ff_r11,label,120,140,768,0,FC(154,165,168),0);
        PS_CAL(c,o38,nx?timer:"--:--",120,176,0,ps_length(timer)>5?150:116,FWHITE);ps_battery(c,s,l,200,phase_color);
    } else if(id==6) { /* BOARD */
        frect(c,20,30,200,22,FC(36,27,5));ftext(c,&ff_m11,"NOW",39,46,0,0,FAMBER,0);
        char now[16];fc_join(now,sizeof(now),l->hour_minute,":",l->seconds);ftext(c,&ff_m11,now,172,46,0,0,FAMBER,0);
        if(l->time_valid&&l->meridiem[0])ftext(c,&ff_r7,l->meridiem,213,46,0,0,FAMBER,0);
        for(unsigned i=0;i<4;i++) {
            int y=58+(int)i*26;uint16_t col=i?FC(201,138,20):FWHITE;
            frect(c,20,y,200,24,i%2?FC(13,10,3):FC(19,15,4));
            if(i>=p->next_count){ftext(c,&ff_m10,i?"--":"NO UPCOMING",120,y+16,0,0,PS_CAP,0);continue;}
            const nova_point_event*e=p->next+i;
            ps_event_clock(clock,e,s->hour_24,false);ftext(c,&ff_m10,clock,49,y+15,0,ps_fit(&ff_m10,clock,0,44),col,0);
            const char*name=ps_label(event_label,e,false,&ff_m11,0,74);
            ftext(c,&ff_m11,name,117,y+15,0,ps_fit(&ff_m11,name,0,74),col,0);
            ps_duration(timer,e->at_rtc-p->now_rtc,true);ftext(c,&ff_m11,timer,190,y+15,0,ps_fit(&ff_m11,timer,0,46),col,0);
            if(e->day_offset){fc_number(clock,(unsigned)e->day_offset);fc_join(label,sizeof(label),"+",clock,"D");ftext(c,&ff_r7,label,49,y+23,0,0,PS_CAP,0);}
        }
        ftext(c,&ff_r9,"LEFT H:MM",186,179,0,0,PS_CAP,0);
        ps_battery(c,s,l,196,FAMBER);
    } else if(id==7) { /* WORKDAY */
        ps_clock(c,l,62,30,FWHITE);ftext(c,&ff_r9,"WORKDAY",120,84,768,0,PS_CAP,0);
        bool paired=p->work_valid&&ps_event_valid(&p->work_start)&&ps_event_valid(&p->work_end)&&
            p->work_start.kind==NOVA_POINT_WORK_START&&p->work_end.kind==NOVA_POINT_WORK_END&&
            !p->work_start.is_end&&!p->work_end.is_end&&p->work_end.at_rtc>p->work_start.at_rtc;
        if(!paired){ftext(c,&ff_r12,"NO WORK PAIR",120,122,384,0,FORANGE,0);ftext(c,&ff_r10,"SET WORK START AND END",120,150,256,0,PS_CAP,0);ps_battery(c,s,l,190,PS_CAP);return;}
        uint32_t start=p->work_start.at_rtc,end=p->work_end.at_rtc;unsigned done=ps_fraction(p->now_rtc,start,end);uint16_t col=done<870?FGREEN:FAMBER;
        fc_round_rect(c,22*16,92*16,196*16,44*16,12*16,PS_BG);
        fc_round_rect(c,22*16,92*16,(int)(196*16*done/1024),44*16,12*16,col);
        /* Only real bounded Lunch/Break end pairs form interruption bands. */
        for(unsigned i=0;i<p->today_count;i++) {
            const nova_point_event*a=p->today+i;if(a->is_end||(a->kind!=NOVA_POINT_LUNCH&&a->kind!=NOVA_POINT_BREAK))continue;
            for(unsigned j=i+1;j<p->today_count;j++){const nova_point_event*b=p->today+j;if(b->kind!=a->kind||b->source_slot!=a->source_slot)continue;if(!b->is_end)break;
                if(b->at_rtc>a->at_rtc&&a->at_rtc<end&&b->at_rtc>start){unsigned x1=ps_fraction(a->at_rtc,start,end),x2=ps_fraction(b->at_rtc,start,end);frect(c,22+(int)(196*x1/1024),92,(int)(196*x2/1024)-(int)(196*x1/1024),44,FC(5,18,13));}break;}
        }
        fc_number(clock,done*100/1024);fc_join(label,sizeof(label),clock,"%","");
        for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++)PS_TEXT(c,o20,label,120+dx,121+dy,0,0,0);
        PS_TEXT(c,o20,label,120,121,0,0,FWHITE);
        if(p->now_rtc<start){ps_duration(timer,start-p->now_rtc,false);fc_join(label,sizeof(label),"WORK STARTS IN ",timer,"");}
        else if(p->now_rtc<end){ps_duration(timer,end-p->now_rtc,false);fc_join(label,sizeof(label),"WORK END IN ",timer,"");}
        else memcpy(label,"WORKDAY COMPLETE",17);
        ftext(c,&ff_r11,label,120,160,512,ps_fit(&ff_r11,label,512,190),PS_PALE,0);
        ps_event_clock(clock,&p->work_start,s->hour_24,false);ftext(c,&ff_r9,clock,65,177,0,0,PS_CAP,0);
        ps_event_clock(clock,&p->work_end,s->hour_24,p->work_end.day_offset!=p->work_start.day_offset);ftext(c,&ff_r9,clock,174,177,0,0,PS_CAP,0);
        ps_battery(c,s,l,196,col);
    } else { /* UP NEXT: attached NOVA-7 Points in Time face. */
        const nova_point_event*active_start=NULL,*active_end=NULL;
        bool active=ps_active_interval(p,&active_start,&active_end);
        const nova_point_event*upcoming=ps_upcoming_start(p,p->now_rtc,false);
        const nova_point_event*primary=active?active_start:upcoming;
        const nova_point_event*target=active?active_end:upcoming;
        uint16_t accent=primary?ps_color(primary):PS_CAP;
        uint32_t target_rtc=target?target->at_rtc:0;
        uint32_t left=target_rtc>p->now_rtc?target_rtc-p->now_rtc:0;
        unsigned bar=0;
        if(active)bar=ps_fraction(p->now_rtc,active_start->at_rtc,active_end->at_rtc);
        else if(upcoming&&p->previous_valid)bar=ps_fraction(p->now_rtc,p->previous.at_rtc,upcoming->at_rtc);
        for(int i=0;i<60;i++)frad(c,i*6*256,i%5?111:105,116,120,120,i%5?16:32,i%5?FC(14,79,92):FCYAN);
        fcirc(c,1920,1920,98*16,40,FC(11,23,25));
        unsigned sub=s->subsecond_ms<1000?s->subsecond_ms:999;
        unsigned second_angle=((unsigned)s->time.second*1000u+sub)*360u*256u/60000u;
        farc(c,98,(int)second_angle,FCYAN,40);
        for(unsigned i=0;i<p->today_count;i++)if(!p->today[i].is_end)ps_up_next_marker(c,p,p->today+i);
        for(unsigned i=0;i<p->next_count;i++)if(!p->next[i].is_end&&p->next[i].day_offset>0)ps_up_next_marker(c,p,p->next+i);
        ftext(c,&ff_r10,l->date,120,58,768,0,FCYAN,0);
        if(primary){const char*prefix=active?"NOW - ":"NEXT - ";fc_join(label,sizeof(label),prefix,ps_label(event_label,primary,false,&ff_r10,512,186-(int)ps_text_width(&ff_r10,prefix,512)-2),"");}
        else memcpy(label,"NO POINTS",10);
        ftext(c,&ff_r10,label,120,76,512,ps_fit(&ff_r10,label,512,186),accent,0);
        ps_clock(c,l,118,34,FWHITE);
        if(target){ps_duration(timer,left,false);fc_join(label,sizeof(label),active?"LEFT ":"IN ",timer,"");}
        else memcpy(label,"ADD A POINT",12);
        ftext(c,&ff_o14,label,120,139,256,ps_fit(&ff_o14,label,256,174),FCYAN,0);
        frect(c,60,146,120,3,FC(18,38,43));if(bar)frect(c,60,146,(int)(120u*bar/1024u),3,accent);
        const nova_point_event*then=NULL;
        if(active)then=upcoming;
        else if(upcoming)then=ps_upcoming_start(p,upcoming->at_rtc,true);
        if(then){char prefix[48];ps_event_clock(clock,then,s->hour_24,true);fc_join(prefix,sizeof(prefix),"THEN ",ps_label(event_label,then,false,&ff_r9,384,188-(int)ps_text_width(&ff_r9,"THEN  ",384)-(int)ps_text_width(&ff_r9,clock,384)-4)," ");fc_join(label,sizeof(label),prefix,clock,"");ftext(c,&ff_r9,label,120,164,384,ps_fit(&ff_r9,label,384,188),PS_CAP,0);}
        else ftext(c,&ff_r9,"THEN --",120,164,384,0,PS_CAP,0);
        for(unsigned i=0;i<10;i++)frect(c,81+(int)i*8,176,6,4,l->battery_valid&&i<s->battery_percent/10?FGREEN:FC(10,32,20));
    }
}
