/* Differential primitive test against the delivered0.6.0 rasterizer.
 * Includes private implementation only in this test, without target state. */
#define WATCH_FACE_RENDER_TEST 1
#include "apps/clock/nova/nova.c"
#include <assert.h>
#include <stdio.h>
static unsigned reference_pixels;
static void reference_line(canvas*c,int x1,int y1,int x2,int y2,int width,uint16_t color) {
    int dx=x2-x1,dy=y2-y1,len=dx*dx+dy*dy,r=width/2;
    int minx=((x1<x2?x1:x2)-r-16)/16,maxx=((x1>x2?x1:x2)+r+16)/16;
    int miny=((y1<y2?y1:y2)-r-16)/16,maxy=((y1>y2?y1:y2)+r+16)/16;
    if(minx<0)minx=0;
    if(miny<0)miny=0;
    if(maxx>239)maxx=239;
    if(maxy>239)maxy=239;
    for(int y=miny;y<=maxy;y++)for(int x=minx;x<=maxx;x++) {
        reference_pixels++;unsigned a=0;
        for(int sy=4;sy<16;sy+=8)for(int sx=4;sx<16;sx+=8) {
            int xx=x*16+sx-x1,yy=y*16+sy-y1,dot=xx*dx+yy*dy;
            if(!len||dot<=0)a+=xx*xx+yy*yy<=r*r;
            else if(dot>=len){xx-=dx;yy-=dy;a+=xx*xx+yy*yy<=r*r;}
            else{int cross=xx*dy-yy*dx;a+=(int64_t)cross*cross<=(int64_t)r*r*len;}
        }
        if(a)blend(at(c,x,y),color,a*255/4);
    }
}

static uint8_t before[240*488+32],after[240*488+32];
static uint32_t random_state=123456789;
static unsigned next_random(void){random_state=random_state*1664525u+1013904223u;return random_state;}
static void compare_line(int x,int y,int xx,int yy,int width) {
    for(unsigned i=0;i<sizeof(before);i++)before[i]=(uint8_t)(i*17u);
    memcpy(after,before,sizeof(before));
    canvas a={before+16,488},b={after+16,488};
    reference_line(&a,x,y,xx,yy,width,0x1234);fline(&b,x,y,xx,yy,width,0x1234);
    assert(!memcmp(before,after,sizeof(before)));
}
void render_sample(void*p,unsigned id,unsigned ms,int picker,int pos,unsigned scale) {
    nova_watch_state state={.time={.year=2026,.month=10,.day=4,.weekday=0,.hour=10,.minute=42,.second=ms/1000%60},.time_valid=true,.battery_valid=true,.battery_percent=84,.subsecond_ms=ms%1000,.animation_ms=42000+ms};
    risc_display_surface_v1 s={0,p,240,240,480,115200,5};nova_watch_picker_cache scratch={0};
    if(picker)assert(nova_watch_picker_render(&s,&state,id,pos,NULL,id,scale,&scratch));else assert(nova_watch_face_render(&s,&state,id));
}
int main(void) {
    compare_line(12*16,12*16,228*16,228*16,32);
    assert(face_test_line_pixels*15u<reference_pixels);
    for(int width=0;width<=128;width+=8) {
        compare_line(0,0,0,0,width);compare_line(-16,0,240*16,0,width);
        compare_line(0,-16,0,240*16,width);compare_line(240*16,240*16,-16,-16,width);
        compare_line(-16,240*16,240*16,-16,width);
    }
    for(unsigned i=0;i<2000;i++) {
        int p[4];for(unsigned j=0;j<4;j++)p[j]=(int)(next_random()%(304*16))-32*16;
        compare_line(p[0],p[1],p[2],p[3],(int)(next_random()%193));
    }
    for(unsigned id=0;id<8;id++) {
        face_test_calls=0;render_sample(after,id,17345,0,0,256);assert(face_test_calls==1);
        face_test_calls=0;render_sample(after,id,17345,1,-(int)id*108*256,256);assert(face_test_calls==(id==0||id==7?2u:3u));
        for(int offset=-80;offset<=80;offset+=4) {
            face_test_calls=0;render_sample(after,id,17345,1,-(int)id*108*256+offset*256,277);assert(face_test_calls<=3);
        }
    }
    /* Cache one focused face plus static visible neighbors. */
    nova_watch_picker_cache cache={0};uint16_t pixels[240*240],frozen[240*240],live[240*240];
    risc_display_surface_v1 surf={0,pixels,240,240,480,sizeof(pixels),5},expected={0,live,240,240,480,sizeof(live),5};
    nova_watch_state state={.time={2026,10,4,0,10,42,18},.time_valid=true,.battery_valid=true,.battery_percent=84,.subsecond_ms=250};
    face_test_calls=0;assert(nova_watch_picker_render(&surf,&state,2,-2*108*256,NULL,8,256,&cache));assert(face_test_calls==3);
    unsigned slot=0;while(cache.face_ids[slot]!=1)slot++;memcpy(frozen,cache.pixels[slot],sizeof(frozen));
    state.subsecond_ms=800;state.animation_ms=1000;state.time.second=19;
    face_test_calls=0;assert(nova_watch_picker_render(&surf,&state,2,-2*108*256,NULL,8,256,&cache));assert(face_test_calls==1);
    assert(!memcmp(frozen,cache.pixels[slot],sizeof(frozen))); /* neighbor froze */
    assert(nova_watch_face_render(&expected,&state,2));unsigned focused=0;while(cache.face_ids[focused]!=2)focused++;
    assert(!memcmp(live,cache.pixels[focused],sizeof(live)));
    /* Changing focus makes the formerly frozen neighbor live immediately. */
    face_test_calls=0;assert(nova_watch_picker_render(&surf,&state,2,-108*256,NULL,8,256,&cache));assert(face_test_calls<=2);
    assert(nova_watch_face_render(&expected,&state,1));assert(!memcmp(live,cache.pixels[slot],sizeof(live)));
    for(unsigned change=0;change<5;change++) {
        if(change==0)state.time.minute++;
        if(change==1)state.time.day++;
        if(change==2)state.battery_percent--;
        if(change==3)state.time_valid=false;
        if(change==4)state.battery_valid=false;
        face_test_calls=0;assert(nova_watch_picker_render(&surf,&state,2,-108*256,NULL,8,256,&cache));assert(face_test_calls==3);
        face_test_calls=0;assert(nova_watch_picker_render(&surf,&state,2,-108*256,NULL,8,256,&cache));assert(face_test_calls==1);
    }
    /* Traverse repeatedly: no stale slot aliases or offscreen work. */
    for(int pos=0;pos>=-7*108*256;pos-=13*256) {
        face_test_calls=0;assert(nova_watch_picker_render(&surf,&state,2,pos,NULL,2,277,&cache));assert(face_test_calls<=3);
    }
    risc_display_surface_v1 invalid={0,after,240,240,480,115199,5};nova_watch_picker_cache scratch={0};
    assert(!nova_watch_picker_render(&invalid,NULL,0,0,NULL,0,256,&scratch));
    invalid.size_bytes++;invalid.pixel_format=4;assert(!nova_watch_picker_render(&invalid,NULL,0,0,NULL,0,256,&scratch));
    puts("2085 capsule strokes exact; diagonal tested work cut >15x; standalone1face and picker<=3visible faces, no discarded render");
}
