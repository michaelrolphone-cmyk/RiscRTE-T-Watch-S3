// Adapted from pinned T5S3 StartupScreen.cpp. See SOURCES.json and reference/LICENSE.
// Output mapping: portrait logical 320x320 -> RGB565 240x240, light ink on black.
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "effects.h"
namespace {
constexpr int kLogoSize=240,kFrameHeight=320;
constexpr uint8_t kLogoLayerCount=4,kFullCoverage=64;
static uint32_t visualTimeMs;
static const struct {int width,height;} videoSurface={320,320};
static void setPhysicalPixel(uint8_t* buffer,size_t bytes,int x,int y,bool ink) {
  if(x<0 || y<0 || x>=320 || y>=320) return;
  const size_t offset=((size_t)(y*3/4)*240+(unsigned)(x*3/4))*2;
  if(offset+2>bytes) return;
  uint16_t value=ink?0xffff:0;memcpy(buffer+offset,&value,2);
}
constexpr uint8_t kBayer8[8][8] = {
    {0, 48, 12, 60, 3, 51, 15, 63},
    {32, 16, 44, 28, 35, 19, 47, 31},
    {8, 56, 4, 52, 11, 59, 7, 55},
    {40, 24, 36, 20, 43, 27, 39, 23},
    {2, 50, 14, 62, 1, 49, 13, 61},
    {34, 18, 46, 30, 33, 17, 45, 29},
    {10, 58, 6, 54, 9, 57, 5, 53},
    {42, 26, 38, 22, 41, 25, 37, 21},
};

struct VideoRect {
  int x;
  int y;
  int width;
  int height;
};

constexpr VideoRect kLogoRects[] = {
    {10, 14, 16, 16},
    {31, 14, 16, 16},
    {52, 14, 16, 16},
    {73, 14, 16, 16},
    {94, 14, 16, 16},
    {10, 38, 47, 16},
    {63, 38, 47, 16},
    {10, 62, 100, 16},
    {10, 86, 100, 24},
};

constexpr uint8_t kLogoLayerEnds[kLogoLayerCount] = {
    5,
    7,
    8,
    9,
};
constexpr uint8_t kLogoBlockCount = kLogoLayerEnds[kLogoLayerCount - 1];



bool ditherPixel(int x, int y, uint8_t coverage) {
  return coverage >= kFullCoverage || kBayer8[y & 7][x & 7] < coverage;
}

bool insideRoundedRect(int px, int py, int width, int height, int radius) {
  if (radius <= 0 || (px >= radius && px < width - radius) ||
      (py >= radius && py < height - radius)) {
    return true;
  }

  const int centerX = px < radius ? radius - 1 : width - radius;
  const int centerY = py < radius ? radius - 1 : height - radius;
  const int dx = px - centerX;
  const int dy = py - centerY;
  return dx * dx + dy * dy <= radius * radius;
}

void drawDitheredRoundedRect(uint8_t* buffer, size_t bufferSize, int x, int y,
                             int width, int height, int radius,
                             uint8_t coverage) {
  for (int py = 0; py < height; ++py) {
    for (int px = 0; px < width; ++px) {
      const int screenX = x + px;
      const int screenY = y + py;
      if (insideRoundedRect(px, py, width, height, radius) &&
          ditherPixel(screenX, screenY, coverage)) {
        setPhysicalPixel(buffer, bufferSize, screenX, screenY, true);
      }
    }
  }
}


struct InkPoint { int x; int y; };

// Fixed-size convex strip rasterizer. All work is clipped to the panel; the
// ribbons use 32 strips each and never allocate a path or framebuffer.
void inkQuad(uint8_t* buffer,size_t size,const InkPoint* p,uint8_t coverage) {
  if(!coverage) return;
  int top=p[0].y,bottom=top;
  for(int i=1;i<4;++i) {if(p[i].y<top) top=p[i].y;if(p[i].y>bottom) bottom=p[i].y;}
  if(top<0) top=0;
  if(bottom>=static_cast<int>(videoSurface.width)) bottom=videoSurface.width-1;
  for(int y=top;y<=bottom;++y) {
    int left=32767,right=-32768;
    for(int i=0;i<4;++i) {
      InkPoint a=p[i],b=p[(i+1)%4];
      if(a.y>b.y) {const InkPoint swap=a;a=b;b=swap;}
      if(a.y==b.y || y<a.y || y>=b.y) continue;
      const int x=a.x+(b.x-a.x)*(y-a.y)/(b.y-a.y);
      if(x<left) left=x;
      if(x>right) right=x;
    }
    if(left<0) left=0;
    if(right>=static_cast<int>(videoSurface.height)) right=videoSurface.height-1;
    for(int x=left;x<=right;++x)
      if(ditherPixel(x,y,coverage)) setPhysicalPixel(buffer,size,x,y,true);
  }
}

InkPoint inkCurve(int t,int side,int cx,int cy) {
  const int64_t q=1000-t;
  const int64_t a=q*q*q,b=3*q*q*t,c=3*q*t*t;
  return {cx+side*static_cast<int>((-330*a+340*b-190*c)/1000000000),
          cy+side*static_cast<int>((-190*a-260*b+190*c)/1000000000)};
}

void drawInkSweep(uint8_t* buffer,size_t size,int cx,int cy,uint32_t time,uint8_t coverage) {
  if(time>=780u || !coverage) return;
  for(int side=-1;side<=1;side+=2) {
    const int local=static_cast<int>(time)-(side==1?70:0);
    if(local<0) continue;
    const int head=local*1500/710;
    const int tail=head-500;
    InkPoint previousA{},previousB{};
    bool previous=false;
    for(int segment=0;segment<=32;++segment) {
      const int along=segment*1000/32;
      const int t=tail+500*along/1000;
      if(t<0 || t>1000) {previous=false;continue;}
      const InkPoint center=inkCurve(t,side,cx,cy);
      const int64_t q=1000-t;
      const int dx=side*static_cast<int>((670*q*q-1060*q*t+190LL*t*t)/1000000);
      const int dy=side*static_cast<int>((-70*q*q+900*q*t-190LL*t*t)/1000000);
      const int ax=dx<0?-dx:dx,ay=dy<0?-dy:dy;
      const int norm=(ax>ay?ax+ay/2:ay+ax/2)+1;
      // Tapered brush body: a broad belly, fine tail and pointed leading edge.
      const int belly=4*along*(1000-along)/1000;
      const int endTaper=t>875?(1000-t)*8:1000;
      const int width=belly*(3+49*(1000-t)*(1000-t)/1000000)/1000*endTaper/1000;
      const InkPoint a{center.x-dy*width/norm,center.y+dx*width/norm};
      const InkPoint b{center.x+dy*width/norm,center.y-dx*width/norm};
      if(previous) {const InkPoint quad[4]={previousA,a,b,previousB};inkQuad(buffer,size,quad,coverage);}
      previousA=a;previousB=b;previous=true;
    }
  }
}

void drawFormingBlock(uint8_t* buffer,size_t size,int x,int y,int width,int height,
                      uint32_t age,int side,uint8_t coverage) {
  if(!coverage) return;
  if(age>=360u) {
    drawDitheredRoundedRect(buffer,size,x,y,width,height,4,coverage);
    return;
  }
  const int t=static_cast<int>(age)*1000/360,q=t-1000;
  // A restrained ease-out-back gives the ink weight and a soft pressure release.
  const int ease=1000+static_cast<int>((2400LL*q*q*q/1000+1400LL*q*q)/1000000);
  const int growth=ease<0?0:ease;
  const int w=2+(width-2)*growth/1000,h=2+(height-2)*growth/1000;
  const int cx=x+width/2+side*30*(1000-ease)/1000;
  const int cy=y+height/2+45*(1000-ease)/1000;
  const int bend=side*w*22*(1000-t)/200000;
  const int radius=4+(h/2-4)*(1000-t)/1000;
  for(int px=0;px<w;++px) {
    const int u=px*1000/(w>1?w-1:1);
    const int curl=bend*4*u*(1000-u)/1000000;
    for(int py=0;py<h;++py) {
      if(!insideRoundedRect(px,py,w,h,radius)) continue;
      const int sx=cx-w/2+px,sy=cy-h/2+py+curl;
      if(ditherPixel(sx,sy,coverage)) setPhysicalPixel(buffer,size,sx,sy,true);
    }
  }
}

// RiscRTE wordmark rasterized from DejaVu Sans Bold, 36 px.
// Font notice: docs/BOOT_WORDMARK_LICENSE.txt. Static flash data; no font/SD load.
constexpr uint8_t kWordmarkWidths[7]={28,12,21,21,28,25,25};
constexpr uint32_t kWordmarkRows[7][32]={
  {0x0u,0x3fff8u,0xffff8u,0x3ffff8u,0x3ffff8u,0x7ffff8u,0x7f01f8u,0x7e01f8u,0x7e01f8u,0x7e01f8u,0x7e01f8u,0x3f01f8u,0x3ffff8u,0x1ffff8u,0x7fff8u,0xffff8u,0x1ffff8u,0x3fc1f8u,0x3f81f8u,0x7f01f8u,0x7e01f8u,0xfe01f8u,0xfe01f8u,0xfc01f8u,0x1fc01f8u,0x1f801f8u,0x3f801f8u,0x0u,0x0u,0x0u,0x0u,0x0u},
  {0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x0u,0x0u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x0u,0x0u,0x0u,0x0u,0x0u},
  {0x0u,0x0u,0x0u,0x0u,0x0u,0x0u,0x0u,0x1ffc0u,0x7fff0u,0x7fff8u,0x7fffcu,0x781fcu,0x400fcu,0xfcu,0x1fcu,0x3ffcu,0x1fff8u,0x7fff0u,0xfff80u,0xfe000u,0xfc000u,0xfc004u,0xfe03cu,0x7fffcu,0x7fffcu,0x3fffcu,0x7fe0u,0x0u,0x0u,0x0u,0x0u,0x0u},
  {0x0u,0x0u,0x0u,0x0u,0x0u,0x0u,0x0u,0xfe00u,0x3ff80u,0x7ffe0u,0x7fff0u,0x7fff8u,0x707f8u,0x401fcu,0x1fcu,0xfcu,0xfcu,0xfcu,0xfcu,0x1fcu,0x401fcu,0x707f8u,0x7fff8u,0x7fff0u,0x7ffe0u,0x3ffc0u,0xfe00u,0x0u,0x0u,0x0u,0x0u,0x0u},
  {0x0u,0x3fff8u,0xffff8u,0x3ffff8u,0x3ffff8u,0x7ffff8u,0x7f01f8u,0x7e01f8u,0x7e01f8u,0x7e01f8u,0x7e01f8u,0x3f01f8u,0x3ffff8u,0x1ffff8u,0x7fff8u,0xffff8u,0x1ffff8u,0x3fc1f8u,0x3f81f8u,0x7f01f8u,0x7e01f8u,0xfe01f8u,0xfe01f8u,0xfc01f8u,0x1fc01f8u,0x1f801f8u,0x3f801f8u,0x0u,0x0u,0x0u,0x0u,0x0u},
  {0x0u,0xffffffu,0xffffffu,0xffffffu,0xffffffu,0xffffffu,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x7e00u,0x0u,0x0u,0x0u,0x0u,0x0u},
  {0x0u,0x3ffff8u,0x3ffff8u,0x3ffff8u,0x3ffff8u,0x3ffff8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1ffff8u,0x1ffff8u,0x1ffff8u,0x1ffff8u,0x1ffff8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x1f8u,0x3ffff8u,0x3ffff8u,0x3ffff8u,0x3ffff8u,0x3ffff8u,0x0u,0x0u,0x0u,0x0u,0x0u}
};

void drawBootWordmark(uint8_t* buffer,size_t size,int centerX,int y,uint8_t coverage) {
  int total=0;for(int i=0;i<7;++i) total+=kWordmarkWidths[i];
  int x=centerX-total/2;
  const uint32_t elapsed=visualTimeMs>1000u?visualTimeMs-1000u:0;
  for(int letter=0;letter<7;++letter) {
    const int width=kWordmarkWidths[letter];
    const int age=static_cast<int>(elapsed)-letter*25;
    if(age>0 && coverage) {
      if(age<130) {
        const int height=27*age/130;
        drawDitheredRoundedRect(buffer,size,x+width/2-3,y+27-height,6,height,1,coverage);
      } else {
        const int unfold=age>=360?1000:(age-130)*1000/230;
        const int eased=unfold*unfold*(3000-2*unfold)/1000000;
        const int drawnWidth=6+(width-6)*eased/1000;
        for(int py=0;py<32;++py) {
          if(letter==1 && py<5) continue; // dot arrives independently below
          for(int dx=0;dx<drawnWidth;++dx) {
            const int sourceX=dx*width/drawnWidth;
            const int px=x+(width-drawnWidth)/2+dx;
            if((kWordmarkRows[letter][py]&(1u<<sourceX)) && ditherPixel(px,y+py,coverage))
              setPhysicalPixel(buffer,size,px,y+py,true);
          }
        }
      }
      if(letter==1 && age>=170) {
        const int fall=age>=340?1000:(age-170)*1000/170;
        int offset=-20+20*fall*fall/1000000;
        if(age>=340 && age<450) {
          const int bounce=(age-340)*1000/110;
          offset=-4*4*bounce*(1000-bounce)/1000000;
        }
        for(int py=0;py<5;++py) for(int px=0;px<width;++px)
          if((kWordmarkRows[letter][py]&(1u<<px)) && ditherPixel(x+px,y+py+offset,coverage))
            setPhysicalPixel(buffer,size,x+px,y+py+offset,true);
      }
    }
    x+=width;
  }
}

void drawVideoLogo(uint8_t* buffer, size_t bufferSize, uint8_t visibleBlocks,
                   uint8_t logoCoverage, uint8_t textCoverage) {
  // Large opening gesture resolves into the stationary brand mark.
  if (visibleBlocks > kLogoBlockCount) visibleBlocks = kLogoBlockCount;

  const int logicalWidth = static_cast<int>(videoSurface.height);
  const int logicalHeight = static_cast<int>(videoSurface.width);
  const int frameX = (logicalWidth - kLogoSize) / 2;
  const int frameY = (logicalHeight - kFrameHeight) / 2;


  drawInkSweep(buffer,bufferSize,logicalWidth/2,frameY+116,visualTimeMs,logoCoverage);
  // The wave follows the arriving ink and leaves the original logo behind.
  for(int rectIndex=0;rectIndex<kLogoBlockCount;++rectIndex) {
    const uint32_t born=400u+static_cast<uint32_t>(rectIndex)*40u;
    if(visualTimeMs<=born) continue;
    const auto& rect=kLogoRects[rectIndex];
    drawFormingBlock(buffer,bufferSize,frameX+rect.x*2,frameY+rect.y*2,
                     rect.width*2,rect.height*2,visualTimeMs-born,
                     (rectIndex&1)?1:-1,logoCoverage);
  }

  // Both labels stay at fixed coordinates and first appear after all blocks.
  if (visibleBlocks == kLogoBlockCount && textCoverage != 0U) {
    drawBootWordmark(buffer,bufferSize,logicalWidth/2,frameY+244,logoCoverage);
    // A quiet three-dot loading beat begins after the wordmark settles.
    if(visualTimeMs>=1510u) for(int dot=0;dot<3;++dot) {
      const int phase=static_cast<int>((visualTimeMs/180u)%3u);
      const int radius=dot==phase?3:2;
      for(int py=-radius;py<=radius;++py) for(int px=-radius;px<=radius;++px) {
        if(px*px+py*py>radius*radius) continue;
        const int x=logicalWidth/2+(dot-1)*13+px,y=frameY+297+py;
        if(ditherPixel(x,y,textCoverage)) setPhysicalPixel(buffer,bufferSize,x,y,true);
      }
    }

  }
}


}
extern "C" bool watch_boot_render(const risc_display_surface_v1* s,uint32_t ms) {
 if(!s || !s->pixels || s->width!=240 || s->height!=240 || s->stride_bytes!=480 || s->size_bytes<115200 || s->pixel_format!=5) return false;
 memset(s->pixels,0,115200);visualTimeMs=ms;
 drawVideoLogo((uint8_t*)s->pixels,115200,9,64,ms>1000?64:0);
 return true;
}
