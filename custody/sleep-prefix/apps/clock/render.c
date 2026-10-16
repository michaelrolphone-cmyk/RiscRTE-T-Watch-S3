#include "render.h"
/* Original 5x7 bitmap glyphs, columns, low bit at top. No external font asset. */
static const uint8_t digits[10][5] = {
    {0x3e,0x51,0x49,0x45,0x3e},{0,0x42,0x7f,0x40,0},{0x62,0x51,0x49,0x49,0x46},
    {0x22,0x41,0x49,0x49,0x36},{0x18,0x14,0x12,0x7f,0x10},{0x27,0x45,0x45,0x45,0x39},
    {0x3c,0x4a,0x49,0x49,0x30},{1,0x71,9,5,3},{0x36,0x49,0x49,0x49,0x36},
    {6,0x49,0x49,0x29,0x1e}
};
static uint8_t column(char c, unsigned i) {
    if (c >= '0' && c <= '9') return digits[c-'0'][i];
    switch (c) {
    case ':': return i == 2 ? 0x24 : 0;
    case '-': return 8;
    case 'A': {const uint8_t a[]={0x7e,9,9,9,0x7e};return a[i];}
    case 'C': {const uint8_t a[]={0x3e,0x41,0x41,0x41,0x22};return a[i];}
    case 'E': {const uint8_t a[]={0x7f,0x49,0x49,0x49,0x41};return a[i];}
    case 'I': {const uint8_t a[]={0,0x41,0x7f,0x41,0};return a[i];}
    case 'K': {const uint8_t a[]={0x7f,8,0x14,0x22,0x41};return a[i];}
    case 'L': {const uint8_t a[]={0x7f,0x40,0x40,0x40,0x40};return a[i];}
    case 'M': {const uint8_t a[]={0x7f,2,0x0c,2,0x7f};return a[i];}
    case 'N': {const uint8_t a[]={0x7f,4,8,0x10,0x7f};return a[i];}
    case 'O': {const uint8_t a[]={0x3e,0x41,0x41,0x41,0x3e};return a[i];}
    case 'P': {const uint8_t a[]={0x7f,9,9,9,6};return a[i];}
    case 'R': {const uint8_t a[]={0x7f,9,0x19,0x29,0x46};return a[i];}
    case 'S': {const uint8_t a[]={0x46,0x49,0x49,0x49,0x31};return a[i];}
    case 'T': {const uint8_t a[]={1,1,0x7f,1,1};return a[i];}
    case 'U': {const uint8_t a[]={0x3f,0x40,0x40,0x40,0x3f};return a[i];}
    default: return 0;
    }
}
static void pixel(risc_display_surface_v1 *s, unsigned x, unsigned y, uint16_t color) {
    if (x < s->width && y < s->height) {
        uint8_t *p=(uint8_t*)s->pixels+y*s->stride_bytes+x*2;
        p[0]=(uint8_t)color;p[1]=(uint8_t)(color>>8);
    }
}
static void label(risc_display_surface_v1 *s, const char *text, unsigned y,
                  unsigned scale, uint16_t color) {
    unsigned length=0;while(text[length])length++;
    unsigned width=length*6*scale-scale;
    unsigned x=width<s->width?(s->width-width)/2:0;
    for(unsigned k=0;k<length;k++) for(unsigned col=0;col<5;col++)
        for(unsigned row=0;row<7;row++) if(column(text[k],col)&(1u<<row))
            for(unsigned dy=0;dy<scale;dy++)for(unsigned dx=0;dx<scale;dx++)
                pixel(s,x+(k*6+col)*scale+dx,y+row*scale+dy,color);
}
static void two(char *out,unsigned value){out[0]='0'+value/10;out[1]='0'+value%10;}
bool watch_clock_render(risc_display_surface_v1 *s,const twatch_rtc_time_v1 *t,
                        bool valid,uint32_t uptime) {
    if(!s || !s->pixels || s->pixel_format!=RISC_DISPLAY_FORMAT_RGB565 ||
       s->width!=240 || s->height!=240 || s->stride_bytes<480 ||
       s->stride_bytes>UINT32_MAX/240 || s->size_bytes<s->stride_bytes*240) return false;
    valid=valid && tw_valid_time(t);
    for(unsigned y=0;y<s->height;y++)for(unsigned x=0;x<s->width;x++)pixel(s,x,y,0x0841);
    label(s,"RISC CLOCK",18,2,0x6b6d);
    char hm[]="--:--",seconds[]="--",date[]="---- -- --";
    if(valid){two(hm,t->hour);two(hm+3,t->minute);two(seconds,t->second);
        two(date,t->year/100);two(date+2,t->year%100);two(date+5,t->month);two(date+8,t->day);}
    label(s,hm,63,7,valid?0xffff:0x7bef);
    label(s,seconds,124,3,valid?0x07ff:0x7bef);
    if(valid)label(s,date,168,2,0xbdf7);
    else label(s,"TIME UNSET",168,2,0xfd20);
    char up[]="UP 000000S";uptime%=1000000;
    for(int i=8;i>=3;i--){up[i]='0'+uptime%10;uptime/=10;}
    label(s,up,218,1,0x6b6d);
    return true;
}
