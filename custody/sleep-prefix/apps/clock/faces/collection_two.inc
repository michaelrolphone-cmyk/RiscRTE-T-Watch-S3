#define WATCH_COLLECTION_TWO_RENDER_INCLUDED 1
/* Watch Faces II: owner-supplied SVG geometry adapted to bounded RGB565.
 * No runtime font engine, allocation, I/O, floating point or sensor invention. */
#include "collection_two_assets.inc"
static uint16_t f2dim(uint16_t c,unsigned a) {
    return (uint16_t)((((c>>11)*a/255)<<11)|(((((c>>5)&63)*a/255))<<5)|((c&31)*a/255));
}
static unsigned f2edge(int x) {
    int d=x<120?2*x+1:479-2*x;
    return d<96?(unsigned)(d*255/96):255u;
}
static void f2fade(canvas*c) {
    for(int y=0;y<240;y++)for(int x=0;x<240;x++)if(x<48||x>=192||y<48||y>=192) {
        uint8_t*p=at(c,(unsigned)x,(unsigned)y);uint16_t col=(uint16_t)(p[0]|p[1]<<8);
        if(col)put(p,f2dim(col,f2edge(x)*f2edge(y)/255));
    }
}
/* Ordered quantization keeps the source's smooth glows from breaking into
 * obvious concentric RGB565 bands. This is spatially stable across frames. */
static void f2gradient_pixel(canvas*c,int x,int y,uint16_t color,unsigned alpha) {
    static const uint8_t threshold[16]={0,8,2,10,12,4,14,6,3,11,1,9,15,7,13,5};
    uint8_t*p=at(c,(unsigned)x,(unsigned)y);unsigned old=p[0]|p[1]<<8,inv=255-alpha,t=threshold[(y&3)*4+(x&3)];
    unsigned r=((old>>11)*inv+(color>>11)*alpha)*16/255;
    unsigned g=(((old>>5)&63)*inv+((color>>5)&63)*alpha)*16/255;
    unsigned b=((old&31)*inv+(color&31)*alpha)*16/255;
    put(p,(uint16_t)((((r+t)/16)<<11)|(((g+t)/16)<<5)|((b+t)/16)));
}
static void f2band(canvas*c,int yq8,int heightq8) {
    int end=yq8+heightq8;
    for(int y=yq8/256;y<(end+255)/256;y++) {
        int lo=y*256>yq8?y*256:yq8,hi=(y+1)*256<end?(y+1)*256:end;
        if(y>=0&&y<240)for(int x=60;x<180;x++)blend(at(c,(unsigned)x,(unsigned)y),0,(unsigned)(hi-lo)*255/256);
    }
}
static void f2blob(canvas*c,int cx,int cy,int radius,uint16_t color) {
    int left=cx-radius,top=cy-radius,right=cx+radius,bottom=cy+radius;
    if(left<0)left=0;
    if(top<0)top=0;
    if(right>239)right=239;
    if(bottom>239)bottom=239;
    unsigned rr=(unsigned)(radius*radius);
    for(int y=top;y<=bottom;y++)for(int x=left;x<=right;x++) {
        int dx=x-cx,dy=y-cy;unsigned d=(unsigned)(dx*dx+dy*dy);
        if(d<rr)f2gradient_pixel(c,x,y,color,f2_radial_alpha[d*1024u/rr]);
    }
}
static void f2battery(canvas*c,const nova_watch_state*s,const nova_watch_labels*l,int y,int width,uint16_t color) {
    int x=120-(10*width+18)/2;unsigned count=l->battery_valid?s->battery_percent/10:0;
    for(unsigned i=0;i<10;i++) {
        uint16_t ink=i<count?color:f2dim(color,41);
        frect(c,x+(int)i*(width+2)+1,y,width-2,4,ink);
        frect(c,x+(int)i*(width+2),y+1,width,2,ink);
    }
}
static void f2battery_label(canvas*c,const nova_watch_labels*l,const char*prefix,int y,uint16_t color) {
    char label[20];unsigned k=0;while(prefix[k]&&k<14){label[k]=prefix[k];k++;}
    for(unsigned i=0;l->battery[i]&&k<19;i++)label[k++]=l->battery[i];
    label[k]=0;
    ftext(c,&ff_r9,label,120,y,512,0,color,0);
}
/* Days after 2000-01-01. Only called after nova_watch_format validated the RTC. */
static unsigned f2days(const twatch_rtc_time_v1*t) {
    static const uint16_t before[]={0,31,59,90,120,151,181,212,243,273,304,334};
    unsigned y=t->year-2000;
    return y*365+(y+3)/4+before[t->month-1]+t->day-1+(t->month>2&&t->year%4==0);
}
/* Same mean synodic month and epoch as the source. This is a visual approximate
 * phase from selected wall-clock RTC fields, not an astronomical ephemeris. */
static unsigned f2moon_phase(const twatch_rtc_time_v1*t,unsigned sub) {
    const int64_t month=2551442803LL;
    int64_t ms=((int64_t)f2days(t)-5)*86400000LL-51840000LL+
        (int64_t)t->hour*3600000+(int64_t)t->minute*60000+t->second*1000+sub;
    ms%=month;if(ms<0)ms+=month;
    return (unsigned)(ms*(360*256)/month);
}
static unsigned f2radians(uint64_t ms,unsigned divisor) {
    /* Reduce a precise fixed-point radians conversion before truncation.
     * Splitting the quotient avoids overflow even for the valid2099 RTC. */
    uint64_t phase=(ms/divisor)*14667719555ULL+(ms%divisor)*14667719555ULL/divisor;
    return (unsigned)((phase%92160000000ULL)/1000000ULL);
}
static unsigned f2sqrt(unsigned n) {
    unsigned r=0,bit=1u<<30;while(bit>n)bit>>=2;
    while(bit){if(n>=r+bit){n-=r+bit;r=(r>>1)+bit;}else r>>=1;bit>>=2;}return r;
}
static void f2moon(canvas*c,unsigned phase) {
    int k=sine(phase+90*256);bool wax=phase<180*256;
    const int r=36*16;
    for(int y=48;y<120;y++) {
        int limb[2];for(int sy=0;sy<2;sy++){int yy=y*16+4+sy*8-84*16;limb[sy]=(int)f2sqrt((unsigned)(r*r-yy*yy));}
        for(int x=84;x<156;x++) {
            unsigned a=0;
            for(int sy=0;sy<2;sy++)for(int sx=4;sx<16;sx+=8) {
                int xx=x*16+sx-120*16,edge=limb[sy],term=k*edge/32767;
                if(xx>=-edge&&xx<=edge&&(wax?xx>=term:xx<=-term))a++;
            }
            if(a)blend(at(c,(unsigned)x,(unsigned)y),FC(235,231,214),a*255/4);
        }
    }
}
static void f2arc(canvas*c,int radius,int start,int end,int cx,int cy,int width,uint16_t color) {
    int px,py;fpoint(start,radius,cx,cy,&px,&py);
    for(int a=start+512;a<end+512;a+=512){int x,y;fpoint(a>end?end:a,radius,cx,cy,&x,&y);fline(c,px,py,x,y,width,color);px=x;py=y;}
}
static int f2lerp(int a,int b,int u){return a+(b-a)*u/4096;}
static int f2smooth(int x){return (x*x/4096)*(12288-2*x)/4096;}
static int f2noise(int x,int y) {
    /* Positive translated source coordinates, tiled only at lookup boundaries. */
    unsigned ix=(unsigned)(x/4096)&127u,iy=(unsigned)(y/4096)&127u;
    int u=f2smooth((int)(x%4096)),v=f2smooth((int)(y%4096));
    int a=f2_noise[iy*128+ix],b=f2_noise[iy*128+((ix+1)&127u)];
    int d=f2_noise[((iy+1)&127u)*128+ix],e=f2_noise[((iy+1)&127u)*128+((ix+1)&127u)];
    return f2lerp(f2lerp(a,b,u),f2lerp(d,e,u),v);
}
static int f2scaled(int x,int factor) {
    /* Positive Q12 coordinates: distribute division exactly to keep every
     * terrain sample32-bit, instead of six64-bit divisions per grid point. */
    return (x/1000)*factor+(x%1000)*factor/1000;
}
static int f2height(int x,int y) {
    return (4*f2noise(f2scaled(x,16),f2scaled(y,16))+2*f2noise(f2scaled(x,34)+29901,f2scaled(y,34))+f2noise(f2scaled(x,70),f2scaled(y,70)+12698))/7;
}
static void f2topo(canvas*c,const nova_watch_state*s) {
    int64_t x=(int64_t)s->animation_ms*6*4096/1000+(int64_t)30*4096*sine(f2radians(s->animation_ms,9000))/32767;
    int64_t y=(int64_t)s->animation_ms*7*4096/2000+(int64_t)22*4096*sine(f2radians(s->animation_ms,11000)+90*256)/32767;
    /* All three source frequencies repeat on the128-cell lattice after
     * 64000 coordinate units. Reduce before narrowing, preserving pixels. */
    int tx=(int)(x%(64000LL*4096)),ty=(int)(y%(64000LL*4096));
    uint16_t height[31*31];
    for(int j=0;j<31;j++)for(int i=0;i<31;i++)height[j*31+i]=(uint16_t)f2height(tx+i*8*4096,ty+j*8*4096);
    static const char*const segments[]={"","LB","BR","LR","TR","TRLB","TB","TL","TL","TB","TLBR","TR","LR","BR","LB",""};
    /* Source HSL ramp including source stroke opacity, quantized to RGB565. */
    static const uint16_t colors[]={FC(16,77,67),FC(20,92,66),FC(23,106,60),FC(29,121,52),FC(36,132,41),FC(58,146,44),FC(88,158,53),FC(121,172,63),FC(153,184,74),FC(190,199,86)};
    for(unsigned n=0;n<10;n++) {
        int level=(int)((300u+45u*n)*65535u/1000u);
        for(int j=0;j<30;j++)for(int i=0;i<30;i++) {
            int a=height[j*31+i],b=height[j*31+i+1],d=height[(j+1)*31+i],e=height[(j+1)*31+i+1];
            unsigned mask=(a>level?8:0)|(b>level?4:0)|(e>level?2:0)|(d>level?1:0);
            const char*sg=segments[mask];if(!*sg)continue;
            int xx=i*128,yy=j*128,px[4],py[4];
            /* Only evaluate intersected edges, avoiding flat-edge division. */
            px[0]=xx+(b!=a?128*(level-a)/(b-a):0);py[0]=yy; /*T*/
            px[1]=xx+128;py[1]=yy+(e!=b?128*(level-b)/(e-b):0); /*R*/
            px[2]=xx+(e!=d?128*(level-d)/(e-d):0);py[2]=yy+128; /*B*/
            px[3]=xx;py[3]=yy+(d!=a?128*(level-a)/(d-a):0); /*L*/
            for(;*sg;sg+=2) {
                unsigned u=sg[0]=='T'?0:sg[0]=='R'?1:sg[0]=='B'?2:3;
                unsigned v=sg[1]=='T'?0:sg[1]=='R'?1:sg[1]=='B'?2:3;
                fline(c,px[u],py[u],px[v],py[v],n%3==2?27:13,colors[n]);
            }
        }
    }
}
static void f2outlined(canvas*c,const face_font*font,const char*s,int y,int spacing,int fit,int radius,uint16_t color) {
    ftext(c,font,s,120-radius,y,spacing,fit,0,0);ftext(c,font,s,120+radius,y,spacing,fit,0,0);
    ftext(c,font,s,120,y-radius,spacing,fit,0,0);ftext(c,font,s,120,y+radius,spacing,fit,0,0);
    ftext(c,font,s,120,y,spacing,fit,color,0);
}
static void f2roundrect(canvas*c,int x,int y,int w,int h,int radius,uint16_t color) {
    frect(c,x+radius,y,w-2*radius,h,color);frect(c,x,y+radius,w,h-2*radius,color);
    for(int i=0;i<2;i++)for(int j=0;j<2;j++)fcirc(c,(x+(i?w-radius:radius))*16,(y+(j?h-radius:radius))*16,radius*16,0,color);
}
static void f2giant(canvas*c,const char*digits,int y) {
    ftext(c,&ff_f2_o104,digits,120,y,0,196,FWHITE,0);
    /* Source objectBoundingBox vertical gradient, separately for each row. */
    int top=y-76,bottom=y+1;
    for(int yy=top;yy<=bottom;yy++)if(yy>=0&&yy<240) {
        int f=(yy-top)*256/(bottom-top);uint16_t col=FC(255,61+115*f/256,110-78*f/256);
        for(int x=0;x<240;x++){uint8_t*p=at(c,(unsigned)x,(unsigned)yy);unsigned a=(unsigned)(p[0]|p[1]<<8);if(a)put(p,f2dim(col,((a>>5)&63)*255/63));}
    }
}
static void fcollection_two(canvas*c,const nova_watch_state*state,const nova_watch_labels*l,unsigned id,int sec,int min,int hour,unsigned sub) {
    if(id==0) {
        uint64_t ms=state->animation_ms;
        if(l->time_valid)ms=((uint64_t)f2days(&state->time)+10957u)*86400000u+(uint64_t)state->time.hour*3600000u+state->time.minute*60000u+state->time.second*1000u+sub;
        int ph=(int)f2radians(ms,9000);
        /* Harmonic phases use original time before reduction, as in HTML. */
        f2blob(c,90+40*sine((unsigned)ph)/32767,80+30*sine(f2radians(ms*13,90000)+90*256)/32767,100,FCYAN);
        f2blob(c,150+40*sine(f2radians(ms*9,90000)+90*256)/32767,150+30*sine(f2radians(ms*11,90000))/32767,100,FC(255,61,203));
        f2blob(c,120+50*sine(f2radians(ms*7,90000)+29335)/32767,120+40*sine(f2radians(ms*8,90000)+90*256)/32767,90,FC(109,91,255));
        f2fade(c);ftext(c,&ff_r12,l->date,120,62,768,0,FC(197,209,217),0);
        ftext(c,&ff_f2_r62,l->hour_minute,120,140,0,150,FWHITE,0);f2battery(c,state,l,180,7,FWHITE);
    } else if(id==1) {
        for(int y=30;y<122;y++)for(int x=74;x<166;x++) {
            int dx=x*16+8-1920,dy=y*16+8-76*16;unsigned count=0;
            if(dx*dx+dy*dy>(46*16+12)*(46*16+12))continue;
            for(int sy=4;sy<16;sy+=8)for(int sx=4;sx<16;sx+=8){int xx=x*16+sx-1920,yy=y*16+sy-76*16;count+=xx*xx+yy*yy<=46*16*46*16;}
            if(count){int f=(y-30)*256/92;blend(at(c,(unsigned)x,(unsigned)y),FC(255,210-165*f/256,74+64*f/256),count*255/4);}
        }
        for(int i=0;i<5;i++)f2band(c,(84+i*8)*256+i*i*154,384+i*230);
        fline(c,40*16,130*16,200*16,130*16,19,FC(255,45,138));f2fade(c);
        ftext(c,&ff_f2_o36,l->hour_minute,120,172,0,124,FWHITE,0);ftext(c,&ff_r10,l->date,120,191,768,0,FC(255,158,201),0);f2battery(c,state,l,203,6,FC(255,210,74));
    } else if(id==2) {
        char hh[3]={l->hour_minute[0],l->hour_minute[1],0};f2giant(c,hh,114);f2giant(c,l->hour_minute+3,196);
        frect(c,22,118,196,2,FC(42,42,42));if(l->time_valid)frect(c,22,118,196*sec/(360*256),2,FWHITE);
        /* SVG scanline pattern repeats every4px:2.4px clear then1.6px black. */
        for(int y=36;y<206;y++){unsigned a=y%4==2?153:y%4==3?255:0;if(a)for(int x=0;x<240;x++)blend(at(c,(unsigned)x,(unsigned)y),0,a);}
        f2fade(c);ftext(c,&ff_r11,l->date,120,30,768,0,FC(191,191,191),0);f2battery(c,state,l,208,7,FC(255,122,61));
    } else if(id==3) {
        for(unsigned i=0;i<46;i++){int v=sine((unsigned)((int64_t)sec*7*14668/(60*256)+i*14668));if(v<0)v=-v;unsigned a=51+(unsigned)v*127/32767;fcirc(c,f2_stars[i*3]*16,f2_stars[i*3+1]*16,f2_stars[i*3+2],0,f2dim(FWHITE,a));}
        f2blob(c,120,84,76,FC(159,180,255));fcirc(c,1920,84*16,36*16,0,FC(21,23,29));fcirc(c,1920,84*16,36*16,16,FC(42,47,58));
        static const char*const names[]={"NEW MOON","WAXING CRESCENT","FIRST QUARTER","WAXING GIBBOUS","FULL MOON","WANING GIBBOUS","LAST QUARTER","WANING CRESCENT"};
        unsigned phase=l->time_valid?f2moon_phase(&state->time,sub):0;if(l->time_valid)f2moon(c,phase);f2fade(c);
        ftext(c,&ff_r9,l->time_valid?names[((phase+5760)/11520)%8]:"PHASE UNSET",120,136,640,0,FC(159,180,255),0);
        ftext(c,&ff_f2_o34,l->hour_minute,120,172,0,116,FWHITE,0);ftext(c,&ff_r10,l->date,120,190,768,0,FMUTED,0);f2battery(c,state,l,203,6,FGREEN);
    } else if(id==4) {
        f2topo(c,state);f2fade(c);
        for(int i=0;i<2;i++)for(int j=0;j<2;j++){int x=i?222:18,y=j?222:18;fline(c,x*16,y*16,(x+(i?-12:12))*16,y*16,16,FC(62,116,98));fline(c,x*16,y*16,x*16,(y+(j?-12:12))*16,16,FC(62,116,98));}
        f2outlined(c,&ff_r10,"DECORATIVE MAP",46,768,0,2,FC(125,232,196));
        f2outlined(c,&ff_f2_o48,l->hour_minute,124,0,130,3,FWHITE);f2outlined(c,&ff_r11,l->date,148,768,0,2,FC(232,255,217));
        f2outlined(c,&ff_r10,"SYNTHETIC TERRAIN",165,512,0,2,FC(125,232,196));
        for(int y=173;y<187;y++)for(int x=72;x<168;x++)blend(at(c,(unsigned)x,(unsigned)y),0,166);
        f2battery(c,state,l,178,7,FC(125,232,196));
    } else if(id==5) {
        f2blob(c,120,92,36,FAMBER);for(int r=26;r<=70;r+=22)fcirc(c,1920,92*16,r*16,16,FC(42,58,82));fcirc(c,1920,92*16,7*16,0,FAMBER);
        if(l->time_valid){int x,y,mx,my;fpoint(hour,26,120,92,&x,&y);fcirc(c,x,y,88,0,FC(125,180,255));fpoint(min,48,120,92,&mx,&my);fcirc(c,mx,my,72,0,FCYAN);
            x=mx+sine((unsigned)(sec*3))*9*16/32767;y=my-sine((unsigned)(sec*3+90*256))*9*16/32767;fcirc(c,x,y,26,0,FWHITE);
            f2arc(c,70,sec-50*256,sec,120,92,24,FC(153,46,92));fpoint(sec,70,120,92,&x,&y);fcirc(c,x,y,56,0,FC(255,77,154));}
        ftext(c,&ff_f2_o24,l->hour_minute,120,192,0,86,FWHITE,0);ftext(c,&ff_r10,l->date,120,207,768,0,FMUTED,0);f2battery(c,state,l,214,6,FGREEN);
    } else if(id==6) {
        ftext(c,&ff_r12,l->date,120,46,768,0,FC(154,163,166),0);static const int xs[]={22,68,130,176};
        for(unsigned i=0;i<4;i++){int x=xs[i];f2roundrect(c,x,64,42,72,6,FC(22,24,27));f2roundrect(c,x,64,42,42,6,FC(27,30,34));frect(c,x,94,42,6,FC(27,30,34));
            char digit[2]={l->hour_minute[i+(i>1)],0};ftext(c,&ff_f2_r54,digit,x+21,118,0,0,FC(242,239,230),0);frect(c,x,99,42,2,0);}
        uint16_t col=f2dim(FC(242,239,230),l->time_valid&&sub<500?255:77);fcirc(c,1920,88*16,48,0,col);fcirc(c,1920,112*16,48,0,col);
        frect(c,22,148,196,3,FC(22,24,27));if(l->time_valid)frect(c,22,148,196*sec/(360*256),3,FC(255,158,31));f2battery_label(c,l,"BATT ",171,FMUTED);f2battery(c,state,l,177,7,FGREEN);
    } else {
        static const uint8_t digits[10][7]={{14,17,19,21,25,17,14},{4,12,4,4,4,4,14},{14,17,1,2,4,8,31},{31,2,4,2,1,17,14},{2,6,10,18,31,2,2},{31,16,30,1,1,17,14},{6,8,16,30,17,17,14},{31,1,2,4,8,8,8},{14,17,17,14,17,17,14},{14,17,17,15,1,2,12}};
        static const int dx[]={22,64,148,190};uint16_t off=FC(27,20,5);
        for(unsigned i=0;i<4;i++){unsigned d=(unsigned)(l->hour_minute[i+(i>1)]-'0');for(unsigned r=0;r<7;r++)for(unsigned j=0;j<5;j++)fcirc(c,(dx[i]+(int)j*7)*16,(76+(int)r*7)*16,42,0,l->time_valid&&d<10&&(digits[d][r]>>(4-j)&1)?FAMBER:off);}
        fcirc(c,1920,90*16,42,0,l->time_valid&&sub<500?FAMBER:off);fcirc(c,1920,104*16,42,0,l->time_valid&&sub<500?FAMBER:off);
        for(unsigned i=0;i<30;i++){int x=296+(int)i*112;uint16_t ink=l->time_valid&&(int)i<sec/(12*256)?FAMBER:off;fcirc(c,x,146*16,29,0,f2dim(ink,f2edge(x/16)));}
        ftext(c,&ff_r12,l->date,120,58,768,0,FC(204,140,25),0);
        for(unsigned i=0;i<10;i++)fcirc(c,(75+(int)i*10)*16,178*16,42,0,l->battery_valid&&i<state->battery_percent/10?FGREEN:FC(11,34,20));
        f2battery_label(c,l,"BATTERY ",198,FC(107,130,136));
    }
}
