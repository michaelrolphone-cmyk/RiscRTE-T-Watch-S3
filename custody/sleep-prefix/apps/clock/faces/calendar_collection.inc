#define WATCH_CALENDAR_COLLECTION_RENDER_INCLUDED 1
/* Calendar + Time: exact owner-supplied layouts with wall-clock date arithmetic.
 * The RTC is already converted by the existing deployment. No host clock,
 * timezone conversion, calendar service, synthetic appointment, or allocation. */
#include "calendar_assets.inc"
#define FC_TEXT(c,font,s,x,y,spacing,fit,color) ftext_alpha(c,&fc_f_##font,s,x,y,spacing,fit,color,0,calendar_alpha)
#define FC_CAP FC(107,130,136)
#define FC_PALE FC(207,233,238)
#define FC_GOLD FC(255,210,74)
#define FC_ORANGE FC(255,158,31)
#define FC_VIOLET FC(178,77,255)
static const char *const fc_months[]={"JANUARY","FEBRUARY","MARCH","APRIL","MAY","JUNE","JULY","AUGUST","SEPTEMBER","OCTOBER","NOVEMBER","DECEMBER"};
static const char *const fc_days[]={"SUNDAY","MONDAY","TUESDAY","WEDNESDAY","THURSDAY","FRIDAY","SATURDAY"};
static bool fc_leap(unsigned y) {return y%4==0&&(y%100!=0||y%400==0);}
static unsigned fc_days_in_month(unsigned y,unsigned m) {
    static const uint8_t days[]={31,28,31,30,31,30,31,31,30,31,30,31};
    return days[m-1]+(m==2&&fc_leap(y));
}
static unsigned fc_day_of_year(unsigned y,unsigned m,unsigned d) {
    static const uint16_t before[]={0,31,59,90,120,151,181,212,243,273,304,334};
    return before[m-1]+d+(m>2&&fc_leap(y));
}
/* Gregorian weekday is derived from the date; an inconsistent RTC weekday
 * cannot make the calendar disagree with the existing formatted date. */
static unsigned fc_weekday(unsigned y,unsigned m,unsigned d) {
    static const uint8_t offsets[]={0,3,2,5,0,3,5,1,4,6,2,4};
    y-=m<3;return (y+y/4-y/100+y/400+offsets[m-1]+d)%7;
}
static unsigned fc_iso_weeks(unsigned y) {
    unsigned first=fc_weekday(y,1,1);return 52+(first==4||(first==3&&fc_leap(y)));
}
static unsigned fc_iso_week(unsigned y,unsigned m,unsigned d) {
    unsigned wd=fc_weekday(y,m,d);int w=((int)fc_day_of_year(y,m,d)+10-(int)(wd?wd:7))/7;
    if(w<1)return fc_iso_weeks(y-1);
    return (unsigned)w>fc_iso_weeks(y)?1u:(unsigned)w;
}
static void fc_shift_date(unsigned*y,unsigned*m,unsigned*d,int delta) {
    /* Only the seven ribbon dates call this, with a bounded -3..3 delta. */
    int day=(int)*d+delta;
    if(day<1){if(*m==1){*m=12;--*y;}else --*m;day+=(int)fc_days_in_month(*y,*m);}
    else if(day>(int)fc_days_in_month(*y,*m)){day-=(int)fc_days_in_month(*y,*m);if(*m==12){*m=1;++*y;}else ++*m;}
    *d=(unsigned)day;
}
static void fc_number(char*out,unsigned value) {
    char reverse[10];unsigned n=0;do{reverse[n++]=(char)('0'+value%10);value/=10;}while(value&&n<10);
    for(unsigned i=0;i<n;i++)out[i]=reverse[n-i-1];
    out[n]=0;
}
static void fc_hour_label(char*out,unsigned hour,bool hour_24) {
    if(!hour_24){hour%=12;if(!hour)hour=12;}
    two(out,hour);out[2]=0;
}
static unsigned fc_join(char*out,unsigned cap,const char*a,const char*b,const char*d) {
    unsigned n=0;const char *parts[]={a,b,d};
    for(unsigned i=0;i<3;i++)for(const char*p=parts[i];*p&&n+1<cap;p++)out[n++]=*p;
    out[n]=0;return n;
}
static uint16_t fc_dim(uint16_t color,unsigned a) {
    return (uint16_t)((((color>>11)*a/255)<<11)|((((color>>5)&63)*a/255)<<5)|((color&31)*a/255));
}
/* Q4 rounded rectangle, clipped before coverage evaluation. */
static void fc_round_rect(canvas*c,int x,int y,int w,int h,int r,uint16_t color) {
    if(w<=0||h<=0)return;
    if(r>w/2)r=w/2;
    if(r>h/2)r=h/2;
    int left=x/16-1,top=y/16-1,right=(x+w+15)/16,bottom=(y+h+15)/16;
    if(left<0)left=0;
    if(top<0)top=0;
    if(right>239)right=239;
    if(bottom>239)bottom=239;
    for(int yy=top;yy<=bottom;yy++)for(int xx=left;xx<=right;xx++) {
        unsigned a=0;
        for(int sy=4;sy<16;sy+=8)for(int sx=4;sx<16;sx+=8) {
            int px=xx*16+sx-x,py=yy*16+sy-y;
            if(px<0||px>=w||py<0||py>=h)continue;
            int dx=px<r?r-px:px>w-r?px-(w-r):0,dy=py<r?r-py:py>h-r?py-(h-r):0;
            a+=dx*dx+dy*dy<=r*r;
        }
        if(a)blend(at(c,(unsigned)xx,(unsigned)yy),color,a*255/4);
    }
}
static void fc_battery(canvas*c,const nova_watch_state*s,const nova_watch_labels*l,int x,int y,int w,uint16_t color) {
    unsigned filled=l->battery_valid?s->battery_percent/10:0;
    int start=x*16-(10*w+18)*8;
    for(unsigned i=0;i<10;i++)fc_round_rect(c,start+(int)i*(w+2)*16,y*16,w*16,64,16,i<filled?color:fc_dim(color,41));
}
static void fc_arc(canvas*c,const fc_ring_pixel*ring,unsigned count,int radius,int width,int start,int end,uint16_t color) {
    if(end<=start)return;
    for(unsigned i=0;i<count;i++)if(ring[i].angle*2u>=(unsigned)start&&ring[i].angle*2u<=(unsigned)end)
        blend(indexed(c,ring[i].pixel),color,ring[i].alpha);
    if(end-start<360*256){int x,y;fpoint(start,radius,120,120,&x,&y);fcirc(c,x,y,width*8,0,color);fpoint(end,radius,120,120,&x,&y);fcirc(c,x,y,width*8,0,color);}
}
static unsigned fc_edge(int x) {
    int distance=x<120?x*2+1:479-x*2;return distance<96?(unsigned)distance*255/96:255;
}
static void fc_fade(canvas*c) {
    for(int y=0;y<240;y++)for(int x=0;x<240;x++)if(x<48||x>=192||y<48||y>=192){
        uint8_t*p=at(c,(unsigned)x,(unsigned)y);uint16_t color=(uint16_t)(p[0]|p[1]<<8);
        if(color)put(p,fc_dim(color,fc_edge(x)*fc_edge(y)/255));
    }
}
static void fcalendar_collection(canvas*c,const nova_watch_state*state,const nova_watch_labels*l,unsigned id,int sec,int min,int hour,unsigned sub) {
    (void)sec;(void)min;(void)hour;
    bool valid=l->time_valid;const twatch_rtc_time_v1*t=&state->time;
    unsigned year=valid?t->year:2000,month=valid?t->month:1,day=valid?t->day:1;
    unsigned wd=valid?fc_weekday(year,month,day):0,dim=fc_days_in_month(year,month),doy=fc_day_of_year(year,month,day),days=365+fc_leap(year);
    char label[40],number[12],date[3]="--",hh[3]={l->hour_minute[0],l->hour_minute[1],0};
    if(valid)two(date,day);
    if(id==0) { /* GRID */
        FC_TEXT(c,o38,l->hour_minute,120,50,0,122,FWHITE);
        if(valid){fc_number(number,year);fc_join(label,sizeof(label),fc_months[month-1]," ",number);}else memcpy(label,"TIME UNSET",11);
        FC_TEXT(c,r10,label,120,72,768,0,FCYAN);
        for(unsigned i=0;i<7;i++){char s[2]={"SMTWTFS"[i],0};FC_TEXT(c,r10,s,42+(int)i*26,90,0,0,FC_CAP);}
        if(valid)for(unsigned k=0,first=fc_weekday(year,month,1);k<dim;k++) {
            unsigned col=(first+k)%7,row=(first+k)/7;int x=42+(int)col*26,y=108+(int)row*16;bool today=k+1==day;
            if(today)fc_round_rect(c,(x-11)*16,(y-12)*16,22*16,15*16,7*16,FCYAN);
            fc_number(number,k+1);FC_TEXT(c,r11b,number,x,y,0,0,today?FC(0,20,24):col%6?FC_PALE:FC_CAP);
        }
        else FC_TEXT(c,r11,"--",120,140,768,0,FC_CAP);
        fc_battery(c,state,l,120,206,7,FCYAN);
    } else if(id==1) { /* RIBBON */
        if(valid){char mon[4]={fc_months[month-1][0],fc_months[month-1][1],fc_months[month-1][2],0};fc_number(number,year);fc_join(label,sizeof(label),mon," ",number);}else memcpy(label,"TIME UNSET",11);
        FC_TEXT(c,r11,label,120,40,1024,0,FC_ORANGE);FC_TEXT(c,o52,l->hour_minute,120,102,0,150,FWHITE);
        for(int i=-3;i<=3;i++) {
            unsigned yy=year,mm=month,dd=day;int x=120+i*29;bool today=i==0;
            if(today&&valid)fc_round_rect(c,(x-13)*16,130*16,26*16,46*16,13*16,FC_ORANGE);
            char initial[2]={'-',0};memcpy(number,"--",3);
            if(valid){fc_shift_date(&yy,&mm,&dd,i);initial[0]=fc_days[fc_weekday(yy,mm,dd)][0];fc_number(number,dd);}
            FC_TEXT(c,r10b,initial,x,148,0,0,today&&valid?FC(26,15,0):FC_CAP);
            FC_TEXT(c,o12,number,x,166,0,0,today&&valid?FC(26,15,0):FC(217,223,224));
        }
        if(valid)fc_number(number,fc_iso_week(year,month,day));else memcpy(number,"--",3);
        fc_join(label,sizeof(label),"WEEK ",number,"");FC_TEXT(c,r9,label,120,196,768,0,FC_CAP);fc_battery(c,state,l,120,206,7,FC_ORANGE);
    } else if(id==2) { /* YEAR */
        for(unsigned i=0;i<12;i++) {
            int start=(int)i*30*256+384,end=(int)i*30*256+7296;
            fc_arc(c,fc_ring_96,COUNT(fc_ring_96),96,7,start,end,FC(28,34,38));
            unsigned fraction=!valid||i>=month?0:i+1<month?65536:((day-1)*24+t->hour)*65536/(dim*24);
            if(fraction)fc_arc(c,fc_ring_96,COUNT(fc_ring_96),96,7,start,start+(int)(6912*fraction/65536),i+1==month?FC_GOLD:FCYAN);
            int x,y;fpoint((int)i*30*256+15*256,80,120,120,&x,&y);char initial[2]={"JFMAMJJASOND"[i],0};
            FC_TEXT(c,r9b,initial,(x+8)/16,(y+8)/16+3,0,0,valid&&i+1==month?FC_GOLD:FC_CAP);
        }
        if(valid){memcpy(label,fc_days[wd],3);label[3]=0;}else memcpy(label,"---",4);
        FC_TEXT(c,r11,label,120,66,1024,0,FC_GOLD);FC_TEXT(c,o42,l->hour_minute,120,126,0,110,FWHITE);
        if(valid)fc_join(label,sizeof(label),fc_months[month-1]," ",date);else memcpy(label,"TIME UNSET",11);
        FC_TEXT(c,r11,label,120,150,768,0,FC_PALE);fc_battery(c,state,l,120,164,7,FGREEN);
    } else if(id==3) { /* 24H */
        fc_arc(c,fc_ring_98,COUNT(fc_ring_98),98,10,0,360*256,FC(18,28,48));
        fc_arc(c,fc_ring_98,COUNT(fc_ring_98),98,10,90*256,270*256,FC(122,85,18));
        for(int i=0;i<24;i++)frad(c,i*15*256,i%6?88:84,i%6?91:93,120,120,i%6?16:32,i%6?FC(74,90,106):FC_PALE);
        for(unsigned i=0;i<4;i++){int x,y;fpoint((int)i*90*256,70,120,120,&x,&y);fc_hour_label(number,i*6,state->hour_24);FC_TEXT(c,o9,number,(x+8)/16,(y+8)/16+3,0,0,FC(138,152,168));}
        if(valid){int angle=(int)((t->hour*3600u+t->minute*60u+t->second)*16u/15u),x,y;frad(c,angle,78,98,120,120,32,FWHITE);fpoint(angle,98,120,120,&x,&y);
            fcirc(c,x,y,8*16,0,FC(30,30,30));fcirc(c,x,y,6*16,0,FC(75,75,75));fcirc(c,x,y,5*16,0,FWHITE);fcirc(c,x,y,2*16,0,FORANGE);}
        FC_TEXT(c,o36,l->hour_minute,120,122,0,104,FWHITE);FC_TEXT(c,r10,l->date,120,142,768,0,FC_PALE);fc_battery(c,state,l,120,156,7,FAMBER);
    } else if(id==4) { /* AGENDA: layout retained; the board has no calendar capability. */
        if(valid){int now=(int)t->hour*3600+(int)t->minute*60+t->second;
            for(int h=(int)t->hour-3;h<=(int)t->hour+4;h++)if(h>=0&&h<=24){int y=120*16+(h*3600-now)*44*16/3600;
                fline(c,110*16,y,216*16,y,16,FC(29,38,42));fc_hour_label(number,(unsigned)h,state->hour_24);FC_TEXT(c,o9,number,96,y/16+3,0,0,FC_CAP);}
            fline(c,110*16,120*16,216*16,120*16,24,FCYAN);fcirc(c,110*16,120*16,56,0,FCYAN);
        }
        fc_fade(c);
        if(valid){char initial[4]={fc_days[wd][0],fc_days[wd][1],fc_days[wd][2],0};fc_number(number,day);fc_join(label,sizeof(label),initial," ",number);}else memcpy(label,"UNSET",6);
        FC_TEXT(c,r10,label,50,56,512,0,FC_ORANGE);FC_TEXT(c,o40,hh,50,108,0,58,FWHITE);FC_TEXT(c,o40,l->hour_minute+3,50,152,0,58,FWHITE);fc_battery(c,state,l,50,176,5,FGREEN);
        /* Explicitly unknown, never “free”, zero events, or sample appointments. */
        frect(c,112,136,108,30,0);FC_TEXT(c,r10b,"CALENDAR",166,148,256,0,FC_CAP);FC_TEXT(c,r9,"UNAVAILABLE",166,161,256,0,FC_CAP);
    } else if(id==5) { /* DATE */
        if(valid){fc_join(label,sizeof(label),fc_days[wd]," \267 ",fc_months[month-1]);}else memcpy(label,"TIME UNSET",11);
        FC_TEXT(c,r11,label,120,40,768,0,FC_VIOLET);FC_TEXT(c,date,date,120,138,0,170,FC_VIOLET);FC_TEXT(c,o28,l->hour_minute,120,168,0,86,FWHITE);
        if(valid)for(unsigned i=0;i<dim;i++){int x=1920-(int)(dim-1)*52+(int)i*104;fcirc(c,x,186*16,i+1==day?48:29,0,i+1==day?FWHITE:i<day?FC_VIOLET:FC(36,26,51));}
        fc_battery(c,state,l,120,203,7,FC_VIOLET);
    } else if(id==6) { /* DOTS */
        unsigned count=valid?days:365;
        for(unsigned i=0;i<count;i++){int x=(326*16+(int)(i%20)*92*16)/10,y=(325*16+(int)(i/20)*92*16)/10;
            if(valid&&i+1==doy){unsigned milliseconds=t->second*1000u+sub;int angle=(int)((uint64_t)milliseconds*3*180*256*1000000/3141592654ULL);int radius=45+14*sine((unsigned)angle)/32767;
                fcirc(c,x,y,radius+24,0,FC(24,24,24));fcirc(c,x,y,radius,0,FWHITE);}
            else fcirc(c,x,y,29,0,valid&&i+1<doy?fc_dim(FCYAN,204):FC(26,38,48));
        }
        fc_fade(c);FC_TEXT(c,o46_halo,l->hour_minute,120,124,0,126,0);FC_TEXT(c,o46,l->hour_minute,120,124,0,126,FWHITE);
        FC_TEXT(c,r11_halo,l->date,120,148,768,0,0);FC_TEXT(c,r11,l->date,120,148,768,0,FC(232,246,255));
        if(valid){char total[12];fc_number(number,doy);fc_number(total,days);unsigned n=fc_join(label,sizeof(label),"DAY ",number," / ");fc_join(label+n,sizeof(label)-n,total,"","");}else memcpy(label,"DAY -- / --",12);
        FC_TEXT(c,r10_halo,label,120,164,768,0,0);FC_TEXT(c,r10,label,120,164,768,0,FCYAN);
        for(unsigned y=176;y<190;y++)for(unsigned x=72;x<168;x++)blend(at(c,x,y),0,179);
        fc_battery(c,state,l,120,181,7,FGREEN);
    } else { /* PROGRESS: Sunday-start week matches the reference. */
        FC_TEXT(c,o40,l->hour_minute,120,46,0,120,FWHITE);FC_TEXT(c,r10,l->date,120,64,768,0,FC_CAP);
        unsigned seconds=valid?t->hour*3600u+t->minute*60u+t->second:0;
        unsigned numerators[]={seconds,wd*86400u+seconds,(day-1)*86400u+seconds,(doy-1)*86400u+seconds};
        unsigned denominators[]={86400u,7*86400u,dim*86400u,days*86400u};
        static const char *const names[]={"DAY","WEEK","MONTH","YEAR"};
        const uint16_t colors[]={FCYAN,FGREEN,FC_GOLD,FC(255,61,113)};
        for(unsigned i=0;i<4;i++) {
            int y=96+(int)i*26;const face_font*font=&fc_f_r10b;int width=0;for(const char*p=names[i];*p;p++){const face_glyph*g=fglyph(font,*p);width+=(g?g->advance:0)+512;}width-=512;
            FC_TEXT(c,r10b,names[i],26+width/512,y+4,512,0,FC(138,152,168));fc_round_rect(c,76*16,(y-3)*16,100*16,6*16,3*16,FC(26,32,36));
            if(valid){fc_round_rect(c,76*16,(y-3)*16,(int)((uint64_t)numerators[i]*1600/denominators[i]),6*16,3*16,colors[i]);fc_number(number,(unsigned)((uint64_t)numerators[i]*100/denominators[i]));fc_join(label,sizeof(label),number,"%","");}else memcpy(label,"--%",4);
            width=0;for(const char*p=label;*p;p++){const face_glyph*g=fglyph(&fc_f_o11,*p);if(g)width+=g->advance;}FC_TEXT(c,o11,label,214-width/512,y+4,0,0,colors[i]);
        }
        fc_join(label,sizeof(label),"BATTERY ",l->battery,"");FC_TEXT(c,r9,label,120,196,512,0,FC_CAP);fc_battery(c,state,l,120,202,7,FGREEN);
    }
}
#undef FC_TEXT
#undef FC_CAP
#undef FC_PALE
#undef FC_GOLD
#undef FC_ORANGE
#undef FC_VIOLET
