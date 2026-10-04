/* Eight attachment-derived faces. Included by nova.c to reuse its validated
 * RGB565 canvas, blending, RTC formatter and integer sine table. */
typedef struct { uint8_t ch; int8_t left,top; uint8_t width,height; uint16_t advance; uint32_t data; } face_glyph;
typedef struct { const face_glyph *glyphs; unsigned count; } face_font;
#include "assets.inc"
#define FC(r,g,b) ((((r)>>3)<<11)|(((g)>>2)<<5)|((b)>>3))
#define FWHITE 0xffffu
#define FCYAN FC(25,227,255)
#define FGREEN FC(61,255,154)
#define FPURPLE FC(193,91,255)
#define FRED FC(255,90,95)
#define FAMBER FC(255,176,32)
#define FORANGE FC(255,122,26)
#define FMUTED FC(125,140,144)
static const char *const face_names[]={"NOVA","ANALOG","RADAR","HEX","TERMINAL","MINIMAL","BINARY","CHRONO","AURORA","HORIZON","GIANT","MOON","TOPO","ORRERY","FLIP","MATRIX","GRID","RIBBON","YEAR","24H","AGENDA","DATE","DOTS","PROGRESS"};
const char *nova_watch_face_name(unsigned id) {return id<WATCH_FACE_COUNT?face_names[id]:face_names[0];}
static const face_glyph *fglyph(const face_font *font,char ch) {
    for(unsigned i=0;i<font->count;i++)if(font->glyphs[i].ch==(uint8_t)ch)return font->glyphs+i;
    return NULL;
}
static void ftext_alpha(canvas *c,const face_font *font,const char *s,int cx,int y,int spacing,int fit,uint16_t color,uint16_t colon,const uint8_t*alpha) {
    int width=0;
    for(const char *p=s;*p;p++){const face_glyph*g=fglyph(font,*p);if(g)width+=g->advance+spacing;}
    if(!width)return;
    width-=spacing;
    int scale=fit?fit*65536/width:256,pen=cx*256-width*scale/512;
    for(;*s;s++) {
        const face_glyph*g=fglyph(font,*s);if(!g)continue;
        int left=pen+g->left*scale,first=left>=0?left/256:(left-255)/256,last=(left+g->width*scale+255)/256;
        for(int dx=first;dx<last;dx++)if(dx>=0&&dx<240) {
            int src=((dx*256+128-left)*256)/scale-128,sx=src>=0?src/256:(src-255)/256;
            unsigned frac=(unsigned)(src-sx*256);
            for(unsigned gy=0;gy<g->height;gy++) {
                int dy=y+g->top+(int)gy;if(dy<0||dy>=240)continue;
                const uint8_t*row=alpha+g->data+gy*g->width;
                unsigned a=sx>=0&&sx<g->width?row[sx]:0,b=sx+1>=0&&sx+1<g->width?row[sx+1]:0;
                blend(at(c,(unsigned)dx,(unsigned)dy),*s==':'&&colon?colon:color,(a*(256-frac)+b*frac+128)>>8);
            }
        }
        pen+=(g->advance+spacing)*scale/256;
    }
}
static void ftext(canvas*c,const face_font*font,const char*s,int cx,int y,int spacing,int fit,uint16_t color,uint16_t colon) {
    ftext_alpha(c,font,s,cx,y,spacing,fit,color,colon,face_alpha);
}
static void frect(canvas*c,int x,int y,int w,int h,uint16_t color) {
    for(int j=y;j<y+h;j++)if(j>=0&&j<240)for(int i=x;i<x+w;i++)if(i>=0&&i<240)put(at(c,i,j),color);
}
/* Q4 round strokes, with four coverage samples per destination pixel. */
#ifdef WATCH_FACE_RENDER_TEST
static unsigned face_test_calls,face_test_line_pixels,face_test_mask;
#endif
static void fline(canvas*c,int x1,int y1,int x2,int y2,int width,uint16_t color) {
    int dx=x2-x1,dy=y2-y1,len=dx*dx+dy*dy,r=width/2;
    int minx=((x1<x2?x1:x2)-r-16)/16,maxx=((x1>x2?x1:x2)+r+16)/16;
    int miny=((y1<y2?y1:y2)-r-16)/16,maxy=((y1>y2?y1:y2)+r+16)/16;
    if(minx<0)minx=0;
    if(miny<0)miny=0;
    if(maxx>239)maxx=239;
    if(maxy>239)maxy=239;
    /* Every covered sample lies within r of a point on the segment. Limit
     * each row to the segment's x range for that row's y +/- r, then expand
     * by r. The extra Q4 unit/pixel makes truncating division conservative.
     * This keeps exactly the same four samples and round endcaps without
     * scanning the empty rectangle around a long diagonal. */
    int lx=x1,ly=y1,hx=x2,hy=y2;
    if(ly>hy){lx=x2;ly=y2;hx=x1;hy=y1;}
    for(int y=miny;y<=maxy;y++) {
        int first=minx,last=maxx;
        if(hy>ly) {
            int lo=y*16+4-r,hi=y*16+12+r;
            if(lo<ly)lo=ly;
            if(hi>hy)hi=hy;
            if(lo>hy||hi<ly)continue;
            int a=lx+(hx-lx)*(lo-ly)/(hy-ly),b=lx+(hx-lx)*(hi-ly)/(hy-ly);
            int left=((a<b?a:b)-r-17)/16,right=((a>b?a:b)+r+17)/16;
            if(left>first)first=left;
            if(right<last)last=right;
        }
        for(int x=first;x<=last;x++) {
#ifdef WATCH_FACE_RENDER_TEST
        face_test_line_pixels++;
#endif
        unsigned a=0;
        for(int sy=4;sy<16;sy+=8)for(int sx=4;sx<16;sx+=8) {
            int xx=x*16+sx-x1,yy=y*16+sy-y1,dot=xx*dx+yy*dy;
            if(!len||dot<=0)a+=xx*xx+yy*yy<=r*r;
            else if(dot>=len){xx-=dx;yy-=dy;a+=xx*xx+yy*yy<=r*r;}
            else{int cross=xx*dy-yy*dx;a+=(int64_t)cross*cross<=(int64_t)r*r*len;}
        }
        if(a)blend(at(c,x,y),color,a*255/4);
        }
    }
}
static void fcirc(canvas*c,int cx,int cy,int radius,int width,uint16_t color) {
    int outer=radius+width/2,inner=radius-width/2;
    if(!width){outer=radius;inner=0;}
    for(int y=(cy-outer-16)/16;y<=(cy+outer+16)/16;y++)if(y>=0&&y<240)
    for(int x=(cx-outer-16)/16;x<=(cx+outer+16)/16;x++)if(x>=0&&x<240) {
        int tx=x*16+8-cx,ty=y*16+8-cy,dist=tx*tx+ty*ty;
        if(dist>(outer+12)*(outer+12)||(inner>12&&dist<(inner-12)*(inner-12)))continue;
        unsigned a=0;
        for(int sy=4;sy<16;sy+=8)for(int sx=4;sx<16;sx+=8){int dx=x*16+sx-cx,dy=y*16+sy-cy,d=dx*dx+dy*dy;a+=d<=outer*outer&&d>=inner*inner;}
        if(a)blend(at(c,x,y),color,a*255/4);
    }
}
static void fpoint(int angle,int radius,int cx,int cy,int*x,int*y) {
    while(angle<0)angle+=360*256;
    *x=cx*16+sine((unsigned)angle)*radius*16/32767;
    *y=cy*16-sine((unsigned)(angle+90*256))*radius*16/32767;
}
static void frad(canvas*c,int angle,int from,int to,int cx,int cy,int width,uint16_t col) {
    int x1,y1,x2,y2;fpoint(angle,from,cx,cy,&x1,&y1);fpoint(angle,to,cx,cy,&x2,&y2);fline(c,x1,y1,x2,y2,width,col);
}
static void farc(canvas*c,int radius,int end,uint16_t color,int width) {
    int px,py;fpoint(0,radius,120,120,&px,&py);
    for(int a=256;a<end+256;a+=256){int x,y;fpoint(a>end?end:a,radius,120,120,&x,&y);fline(c,px,py,x,y,width,color);px=x;py=y;}
}
static void fbattery(canvas*c,const nova_watch_state*s,const nova_watch_labels*l,int y,int width,int spacing,bool segments,const char*prefix,uint16_t labelcolor) {
    char b[20];unsigned k=0;while(prefix[k]&&k<12){b[k]=prefix[k];k++;}for(unsigned j=0;l->battery[j]&&k<19;j++)b[k++]=l->battery[j];b[k]=0;
    ftext(c,&ff_r9,b,120,y-6,512,0,labelcolor,0);
    bool valid=l->battery_valid;unsigned percent=valid?s->battery_percent:0;
    if(segments){int x=120-(10*width+9*spacing)/2;for(unsigned i=0;i<10;i++)frect(c,x+(int)i*(width+spacing),y,width,5,valid&&i<percent/10?FGREEN:FC(10,32,20));}
    else{frect(c,120-width/2,y,width,3,FC(10,32,20));frect(c,120-width/2,y,(int)(width*percent/100),3,FGREEN);}
}
#include "collection_two.inc"
#include "calendar_collection.inc"
static bool face_surface_valid(const risc_display_surface_v1*s) {
    return s&&s->pixels&&s->pixel_format==5&&s->width==240&&s->height==240&&s->stride_bytes>=480&&s->stride_bytes<=UINT32_MAX/240&&s->size_bytes>=s->stride_bytes*240;
}
bool nova_watch_face_render(risc_display_surface_v1*s,const nova_watch_state*state,unsigned id) {
    if(!face_surface_valid(s))return false;
#ifdef WATCH_FACE_RENDER_TEST
    face_test_calls++;
#endif
    nova_watch_state empty={0};if(!state)state=&empty;if(id>=WATCH_FACE_COUNT)id=0;
#ifdef WATCH_FACE_RENDER_TEST
    face_test_mask|=1u<<id;
#endif
    nova_watch_labels l;nova_watch_format(state,&l);
    /* Use the shared format policy; analog geometry below still uses civil
     * time. Never overwrite the configured twelve-hour labels with RTC hours. */
    unsigned sub=state->subsecond_ms<1000?state->subsecond_ms:999;
    int sec=l.time_valid?(int)(state->time.second*1000u+sub)*1536/1000:0;
    int min=l.time_valid?(int)state->time.minute*1536+sec/60:0;
    int hour=l.time_valid?(int)(state->time.hour%12)*7680+min/12:0;
    canvas c={(uint8_t*)s->pixels,s->stride_bytes};for(unsigned y=0;y<240;y++)memset(at(&c,0,y),0,480);
    char hms[9];memcpy(hms,l.hour_minute,5);hms[5]=':';memcpy(hms+6,l.seconds,3);
    if(id>=16)fcalendar_collection(&c,state,&l,id-16,sec,min,hour,sub);
    else if(id>=8)fcollection_two(&c,state,&l,id-8,sec,min,hour,sub);
    else if(id==0) {
        for(int i=0;i<60;i++)frad(&c,i*1536,i%5?111:105,116,120,120,i%5?16:32,i%5?FC(14,79,92):FCYAN);
        fcirc(&c,1920,1920,98*16,40,FC(11,23,25));if(l.time_valid){farc(&c,98,sec,FC(5,45,51),88);farc(&c,98,sec,FCYAN,40);}
        ftext(&c,&ff_r12,l.date,120,64,640,0,l.time_valid?FCYAN:FORANGE,0);
        ftext(&c,&ff_o40,l.hour_minute,120,128,0,132,FWHITE,sub<500?FCYAN:FC(6,56,63));
        ftext(&c,&ff_o10,l.seconds,120,150,0,0,FCYAN,0);frect(&c,46,158,148,1,FC(14,79,92));
        fbattery(&c,state,&l,182,50,0,false,"BATTERY ",FMUTED);
    } else if(id==1||id==7) {
        for(int i=0;i<60;i++)frad(&c,i*1536,i%5?111:id==7?104:102,116,120,120,i%5?16:i%15||id==7?48:64,i%5?FC(68,68,68):FWHITE);
        ftext(&c,&ff_r10,"NOVA",120,84,1024,0,id==1?FC(136,136,136):FORANGE,0);
        if(id==1){ftext(&c,&ff_r11,l.date,120,154,512,0,FC(136,136,136),0);fbattery(&c,state,&l,176,30,0,false,"BATT ",FGREEN);}
        else{
            ftext(&c,&ff_r9,"CHRONO",120,160,768,0,FC(136,136,136),0);fbattery(&c,state,&l,178,7,2,true,"BATT ",FMUTED);
            fcirc(&c,76*16,1920,26*16,24,FC(68,68,68));fcirc(&c,164*16,1920,26*16,24,FC(68,68,68));
            for(int i=0;i<12;i++)frad(&c,i*7680,22,26,76,120,16,FC(119,119,119));
            if(l.time_valid){frad(&c,sec,-6,22,76,120,24,FORANGE);fcirc(&c,76*16,1920,40,0,FORANGE);}
            ftext(&c,&ff_r7,"DATE",164,108,384,0,FC(136,136,136),0);char day[3]="--";if(l.time_valid){if(state->time.day<10){day[0]=(char)('0'+state->time.day);day[1]=0;}else two(day,state->time.day);}ftext(&c,&ff_o16,day,164,126,0,0,FWHITE,0);
        }
        if(l.time_valid){frad(&c,hour,id==1?-12:-10,56,120,120,id==1?96:80,FWHITE);frad(&c,min,id==1?-14:-12,id==1?86:88,120,120,id==1?64:56,FWHITE);
        if(id==1){frad(&c,sec,-24,98,120,120,26,FORANGE);fcirc(&c,1920,1920,96,0,0);fcirc(&c,1920,1920,96,32,FORANGE);}else{frad(&c,min,60,88,120,120,56,FORANGE);fcirc(&c,1920,1920,80,0,FORANGE);}}
        else ftext(&c,&ff_r12,"TIME UNSET",120,128,256,0,FORANGE,0);
    } else if(id==2) {
        for(int r=32;r<=96;r+=32)fcirc(&c,1920,1920,r*16,16,FC(15,58,36));
        frad(&c,0,-96,96,120,120,16,FC(15,58,36));frad(&c,90*256,-96,96,120,120,16,FC(15,58,36));
        fcirc(&c,1920,1920,110*16,24,FGREEN);for(int i=0;i<12;i++)frad(&c,i*7680,104,110,120,120,24,FGREEN);
        if(l.time_valid){for(int i=59;i>=0;i--)frad(&c,sec-i*256,0,96,120,120,32,FC(61*(60-i)/200,255*(60-i)/200,154*(60-i)/200));frad(&c,sec,0,96,120,120,24,FGREEN);}
        static const uint8_t rr[]={40,70,85,25};static const unsigned aa[]={30,140,250,200};
        for(unsigned i=0;i<4;i++){
            int x,y;fpoint(aa[i]*256,rr[i],120,120,&x,&y);
            unsigned age=(unsigned)(sec+360*256-(int)aa[i]*256)%(360*256);
            int alpha=l.time_valid?255-(int)(age*255/(200*256)):31;if(alpha<31)alpha=31;
            fcirc(&c,x,y,48,0,FC(61*alpha/255,alpha,154*alpha/255));
        }
        for(int dy=-2;dy<=2;dy++)for(int dx=-2;dx<=2;dx++)ftext(&c,&ff_o26,l.hour_minute,120+dx,128+dy,0,0,0,0);
        ftext(&c,&ff_o26,l.hour_minute,120,128,0,0,FWHITE,0);
        for(int dy=-2;dy<=2;dy++)for(int dx=-2;dx<=2;dx++)ftext(&c,&ff_r10,l.date,120+dx,150+dy,512,0,0,0);
        ftext(&c,&ff_r10,l.date,120,150,512,0,FGREEN,0);frect(&c,68,162,104,24,0);fbattery(&c,state,&l,176,7,2,true,"BATT ",FGREEN);
    } else if(id==3) {
        for(int r=100;r<=112;r+=12)for(int i=0;i<6;i++){int x,y,a,b;fpoint(i*60*256,r,120,120,&x,&y);fpoint((i+1)*60*256,r,120,120,&a,&b);fline(&c,x,y,a,b,r==112?48:16,FC(42,15,58));
          if(r==112&&l.time_valid){int portion=sec-i*60*256;if(portion>0){if(portion>60*256)portion=60*256;int ex=x+(a-x)*portion/(60*256),ey=y+(b-y)*portion/(60*256);
            fline(&c,x,y,ex,ey,112,FC(18,8,24));fline(&c,x,y,ex,ey,80,FC(48,22,64));fline(&c,x,y,ex,ey,48,FPURPLE);}}}
        ftext(&c,&ff_r11,l.date,120,58,640,0,FPURPLE,0);char hh[3]={l.hour_minute[0],l.hour_minute[1],0};ftext(&c,&ff_o54,hh,120,110,0,88,FWHITE,0);ftext(&c,&ff_o54,l.hour_minute+3,120,170,0,88,FPURPLE,0);ftext(&c,&ff_o12,l.battery,120,198,0,0,FGREEN,0);
    } else if(id==4) {
        for(int side=0;side<2;side++)for(int bottom=0;bottom<2;bottom++){int x=side?210:30,y=bottom?200:40;fline(&c,x*16,y*16,(x+(side?-14:14))*16,y*16,24,FAMBER);fline(&c,x*16,y*16,x*16,(y+(bottom?-14:14))*16,24,FAMBER);}
        ftext(&c,&ff_m11,"> RISCRTE",120,62,0,0,FAMBER,0);
        unsigned u=state->animation_ms/1000;char up[]="UPTIME 00:00:00";two(up+7,u/3600%100);two(up+10,u/60%60);two(up+13,u%60);ftext(&c,&ff_m10,up,120,80,0,0,FC(47,156,102),0);
        ftext(&c,&ff_m34,hms,120,122,0,166,FGREEN,0);char date[]="DATE ---- -- --";if(l.time_valid){two(date+5,state->time.year/100);two(date+7,state->time.year%100);date[9]='-';two(date+10,state->time.month);date[12]='-';two(date+13,state->time.day);}ftext(&c,&ff_m11,date,120,146,0,0,FGREEN,0);
        ftext(&c,&ff_m11,"BATT",51,164,0,0,FGREEN,0);for(unsigned i=0;i<10;i++)frect(&c,70+(int)i*6,155,5,10,l.battery_valid&&i<state->battery_percent/10?FGREEN:FC(10,32,20));ftext(&c,&ff_m11,l.battery,164,164,0,0,FGREEN,0);ftext(&c,&ff_m11,">",115,184,0,0,FAMBER,0);if(sub<500)frect(&c,123,174,6,11,FAMBER);
    } else if(id==5) {
        ftext(&c,&ff_r12,l.date,120,60,768,0,FRED,0);ftext(&c,&ff_o56,l.hour_minute,120,126,0,172,FWHITE,FRED);frect(&c,60,146,120,2,FC(28,28,28));if(l.time_valid)frect(&c,60,146,sec/(3*256),2,FRED);fbattery(&c,state,&l,180,7,2,true,"BATT ",FMUTED);
    } else {
        fcirc(&c,1920,1920,112*16,24,FC(26,18,4));static const int xs[]={48,76,108,136,168,196};unsigned k=0;
        for(unsigned i=0;i<8;i++)if(hms[i]!=':'){for(unsigned j=0;j<4;j++)fcirc(&c,xs[k]*16,(76+(int)j*26)*16,128,0,l.time_valid&&((hms[i]-'0')>>(3-j)&1)?FAMBER:FC(36,26,5));k++;}
        ftext(&c,&ff_o10,"B C D",120,50,1536,0,FAMBER,0);ftext(&c,&ff_o9,"HH",62,178,0,0,FMUTED,0);ftext(&c,&ff_o9,"MM",122,178,0,0,FMUTED,0);ftext(&c,&ff_o9,"SS",182,178,0,0,FMUTED,0);ftext(&c,&ff_o14,hms,120,198,0,0,FWHITE,0);char bat[10]="BAT ";unsigned i=0;while(l.battery[i]){bat[4+i]=l.battery[i];i++;}bat[4+i]=0;ftext(&c,&ff_o9,bat,120,216,512,0,FGREEN,0);
    }
    if(l.time_valid&&!state->hour_24)ftext(&c,&ff_r9,l.meridiem,217,233,128,0,FMUTED,0);
    return true;
}
/* Rendered previews are the exact same production face function. Scratch is
 * app-owned, allocated only while browsing, and never a provider frame lease.
 * Three full-resolution slots preserve sampling at every card scale. */
unsigned nova_watch_picker_pulse(uint32_t age_ms) {
    if(age_ms>=334u)return 256u;
    return 256u+(unsigned)(sine(age_ms*180u*256u/334u)*5243/(32767*256));
}
typedef struct { const watch_face_page*page; int position,y,near; } picker_layer;
static bool picker_layers_render(risc_display_surface_v1*s,const nova_watch_state*state,unsigned selected,picker_layer*layers,unsigned layer_count,unsigned live_face,const char*status,unsigned pulse_face,unsigned pulse_scale,nova_watch_picker_cache*cache) {
    if(!cache||!layer_count||layer_count>2||!face_surface_valid(s))return false;
    for(unsigned l=0;l<layer_count;l++) {
        const watch_face_page*page=layers[l].page;
        if(!page||!page->ids||!page->count||page->count>WATCH_FACE_COUNT)return false;
        for(unsigned i=0;i<page->count;i++)if(page->ids[i]>=WATCH_FACE_COUNT)return false;
    }
    nova_watch_state empty={0};if(!state)state=&empty;
    /* Neighbor seconds and subsecond animation freeze while out of focus.
     * Refresh visible caches on minute/date or telemetry changes, never merely
     * because a new animation frame has arrived. No offscreen work is done. */
    const nova_watch_state*old=&cache->stamp;
    if(cache->valid_mask&&(old->hour_24!=state->hour_24||old->time_valid!=state->time_valid||old->battery_valid!=state->battery_valid||
        old->battery_percent!=state->battery_percent||old->time.year!=state->time.year||
        old->time.month!=state->time.month||old->time.day!=state->time.day||
        old->time.hour!=state->time.hour||old->time.minute!=state->time.minute))cache->valid_mask=0;
    cache->stamp=*state;
    canvas c={(uint8_t*)s->pixels,s->stride_bytes};for(unsigned y=0;y<240;y++)memset(at(&c,0,y),0,480);

    struct card { int size,x,y,scale; bool visible; } cards[WATCH_FACE_COUNT]={0};
    for(unsigned l=0;l<layer_count;l++) {
        const watch_face_page*page=layers[l].page;int position=layers[l].position;
        int near=(-position+54*256)/(108*256);if(near<0)near=0;if(near>=(int)page->count)near=(int)page->count-1;
        layers[l].near=near;
        for(unsigned index=0;index<page->count;index++) {
            unsigned id=page->ids[index];
            int offset=(int)index*108*256+position,abs=offset<0?-offset:offset;
            int scale=256-(abs<135*256?abs:135*256)*102/(108*256);
            if(id==pulse_face&&pulse_scale>=256&&pulse_scale<=277)scale=scale*(int)pulse_scale/256;
            int size=132*scale/256,x=120+offset/256-size/2,y=92-size/2+layers[l].y;
            cards[id]=(struct card){size,x,y,scale,x<240&&x+size>0&&y<240&&y+size>0};
        }
    }
    for(unsigned l=0;l<layer_count;l++) {
    const watch_face_page*page=layers[l].page;int position=layers[l].position,near=layers[l].near,dy=layers[l].y;
    /* Far cards first, center card last, as in the source z-index. */
    for(int pass=(int)page->count-1;pass>=0;pass--)for(unsigned index=0;index<page->count;index++) {
        unsigned id=page->ids[index];
        int offset=(int)index*108*256+position,abs=offset<0?-offset:offset;
        if((int)index!=near-pass&&(int)index!=near+pass)continue;
        if(!pass&&index!=(unsigned)near)continue;
        if(!cards[id].visible)continue;
        int scale=cards[id].scale,size=cards[id].size,x0=cards[id].x,y0=cards[id].y;
        unsigned slot=6;
        for(unsigned k=0;k<6;k++)if((cache->valid_mask&(1u<<k))&&cache->face_ids[k]==id){slot=k;break;}
        bool cached=slot<6;
        if(!cached)for(unsigned k=0;k<6;k++)if(!(cache->valid_mask&(1u<<k))||!cards[cache->face_ids[k]].visible){slot=k;break;}
        if(slot==6)return false; /* At most three cards per visible collection. */
        uint16_t*scratch=cache->pixels[slot];
        if(!cached||id==live_face) {
            risc_display_surface_v1 tmp={0,scratch,240,240,480,240*240*2,5};
            if(!nova_watch_face_render(&tmp,state,id))return false;
            cache->face_ids[slot]=(uint8_t)id;cache->valid_mask|=(uint8_t)(1u<<slot);
        }
        int radius=14*scale/256,border=id==selected?2*scale/256:scale/256;if(border<1)border=1;
        unsigned opacity=255-(unsigned)(abs<108*256?abs:108*256)*128/(108*256);
        for(int y=0;y<size;y++)for(int x=0;x<size;x++)if(x+x0>=0&&x+x0<240&&y+y0>=0&&y+y0<240){
            int edge=x<radius?radius-x:x>=size-radius?x-(size-radius-1):0,ey=y<radius?radius-y:y>=size-radius?y-(size-radius-1):0;
            if(edge&&ey&&edge*edge+ey*ey>radius*radius)continue;
            uint16_t col=scratch[(y*240/size)*240+x*240/size];unsigned mask=x+x0<46?(unsigned)(x+x0)*255/46:x+x0>194?(unsigned)(239-x-x0)*255/45:255;
            blend(at(&c,x+x0,y+y0),col,opacity*mask/255);
            if(x<border||x>=size-border||y<border||y>=size-border||(edge&&ey&&edge*edge+ey*ey>=(radius-border)*(radius-border)))blend(at(&c,x+x0,y+y0),id==selected?FCYAN:FC(34,48,52),opacity*mask/255);
        }
    }
    ftext(&c,&ff_o13,face_names[page->ids[near]],120,183+dy,532,0,FWHITE,0);
    ftext(&c,&ff_rp11,status?status:(page->ids[near]==selected?"CURRENT":"TAP TO SET"),120,201+dy,563,0,status?FORANGE:page->ids[near]==selected?FGREEN:FC(107,130,136),0);
    for(unsigned i=0;i<page->count;i++)fcirc(&c,(240-(int)(page->count-1)*11+(int)i*22)*8,(222+dy)*16+8,40,0,(int)i==near?FCYAN:FC(31,42,45));
    if(page->name){ftext(&c,&ff_rp11,page->name,120,15+dy,384,0,FMUTED,0);fline(&c,36*16,(12+dy)*16,39*16,(9+dy)*16,16,FMUTED);fline(&c,39*16,(9+dy)*16,42*16,(12+dy)*16,16,FMUTED);fline(&c,198*16,(9+dy)*16,201*16,(12+dy)*16,16,FMUTED);fline(&c,201*16,(12+dy)*16,204*16,(9+dy)*16,16,FMUTED);}
    }
    return true;
}

bool nova_watch_picker_render(risc_display_surface_v1*s,const nova_watch_state*state,unsigned selected,int position,const watch_face_page*page,const char*status,unsigned pulse_face,unsigned pulse_scale,nova_watch_picker_cache*cache) {
    if(!page||!page->ids||!page->count||page->count>WATCH_FACE_COUNT)return false;
    int near=(-position+54*256)/(108*256);if(near<0)near=0;if(near>=(int)page->count)near=(int)page->count-1;
    picker_layer layer={page,position,0,near};
    return picker_layers_render(s,state,selected,&layer,1,page->ids[near],status,pulse_face,pulse_scale,cache);
}
bool nova_watch_picker_collections_render(risc_display_surface_v1*s,const nova_watch_state*state,unsigned selected,int category_position,const int positions[WATCH_FACE_CATEGORY_COUNT],const char*status,unsigned pulse_face,unsigned pulse_scale,nova_watch_picker_cache*cache) {
    if(!positions)return false;
    picker_layer layers[2];unsigned count=0;
    const int period=(int)WATCH_FACE_CATEGORY_COUNT*240;
    category_position%=period*256;if(category_position>0)category_position-=period*256;
    unsigned focus=(unsigned)((-category_position+120*256)/(240*256))%WATCH_FACE_CATEGORY_COUNT;
    const watch_face_page*focused=watch_face_page_for((unsigned)focus);
    int near=(-positions[focus]+54*256)/(108*256);if(near<0)near=0;if(near>=(int)focused->count)near=(int)focused->count-1;
    for(unsigned c=0;c<WATCH_FACE_CATEGORY_COUNT;c++) {
        int y=(category_position<0?(category_position-255)/256:category_position/256)+(int)c*240;
        if(y>period/2)y-=period;
        if(y<-period/2)y+=period;
        if(y<=-240||y>=240)continue;
        if(count==2)return false;
        layers[count++]=(picker_layer){watch_face_page_for(c),positions[c],y,0};
    }
    return picker_layers_render(s,state,selected,layers,count,focused->ids[near],status,pulse_face,pulse_scale,cache);
}
