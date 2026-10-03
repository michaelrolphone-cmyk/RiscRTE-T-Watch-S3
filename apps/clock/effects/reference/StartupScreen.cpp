#include "StartupScreen.h"
#include "native/NativeTouchInput.h"

#include <Arduino.h>
#include <HalDisplay.h>
#include <cstring>
#include <atomic>

#if defined(BOARD_T5S3_PRO) || defined(BOARD_T5S3)
#include <T5HardwareTakeover.h>
#include <T5VideoApi.h>
#include <esp_err.h>
#include <esp_log.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#endif

namespace StartupScreen {
namespace {

bool fadePending = false;  // RenderLock protects the display handoff.
std::atomic<bool> loading{false};  // Input opens only after the first destination frame.

enum class BootBackend : uint8_t {
  None,
  Renderer,
  Video,
};

BootBackend bootBackend = BootBackend::None;

constexpr int kLogoSize = 240;
constexpr int kFrameHeight = 320;

void drawBootFrame(GfxRenderer& renderer, int rows) {
  renderer.clearScreen();

  // Geometry from docs/logo.svg, enlarged twofold for the monochrome panel.
  struct Rect {
    int x;
    int y;
    int width;
    int height;
  };

  constexpr Rect rectangles[] = {
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

  constexpr int rowEnds[] = {
      5,
      7,
      8,
      9,
  };

  const int x = (renderer.getScreenWidth() - kLogoSize) / 2;
  const int y = (renderer.getScreenHeight() - kFrameHeight) / 2;

  for (int i = 0; i < rowEnds[rows - 1]; ++i) {
    const auto& rect = rectangles[i];

    renderer.fillRoundedRect(
        x + rect.x * 2,
        y + rect.y * 2,
        rect.width * 2,
        rect.height * 2,
        4,
        Color::Black);
  }

  if (rows == 4) {
    renderer.drawCenteredText(
        UI_12_FONT_ID,
        y + 250,
        "RiscRTE",
        true,
        EpdFontFamily::BOLD);

    renderer.drawCenteredText(
        SMALL_FONT_ID,
        y + 290,
        "Starting...");
  }
}

void bootWithRenderer(GfxRenderer& renderer) {
  const auto mode = renderer.getRenderMode();
  renderer.setRenderMode(GfxRenderer::BW);
  // Slow-panel fallback presents one useful loading frame, without spending
  // several physical refreshes playing an animation before doing any work.
  drawBootFrame(renderer, 4);
  renderer.displayBuffer(DisplayPresentMode::Quality);
  renderer.setRenderMode(mode);
  bootBackend = BootBackend::Renderer;
}

#if defined(BOARD_T5S3_PRO) || defined(BOARD_T5S3)

constexpr char kBootVideoTag[] = "boot_video";
constexpr uint8_t kLogoLayerCount = 4;
constexpr uint32_t kRevealLayerMs = 250;
constexpr uint32_t kTextFadeMs = 300;
constexpr uint8_t kTextFadeFrames = 6;
constexpr uint32_t kRevealDeadlineMs = 1800;
constexpr uint8_t kFadeFrames = 6;
constexpr uint8_t kPulseFrames = 48;
constexpr uint8_t kFullCoverage = 64;
constexpr uint8_t kPulseMinCoverage = kFullCoverage;
constexpr uint8_t kPulseMaxCoverage = kFullCoverage;
constexpr uint32_t kReadyFadeBudgetMs = 150;
constexpr uint32_t kSubmitTimeoutMs = 350;
constexpr uint32_t kIdleTimeoutMs = 1800;

extern "C" esp_err_t native_hardware_takeover_begin(uint32_t requested);
extern "C" esp_err_t native_hardware_takeover_end(uint32_t requested);

const t5_video_api_v1* videoApi = nullptr;
t5_video_surface_v1 videoSurface{};
bool videoTakeoverActive = false;
bool videoStarted = false;
TaskHandle_t pulseTaskHandle = nullptr;
std::atomic<bool> pulseStopRequested{false};
std::atomic<bool> pulseExited{true};
// Written only by the animation worker; read after its release/acquire join.
uint8_t lastVisibleBlocks = 0;
uint8_t lastPulseCoverage = kFullCoverage;
uint8_t lastTextCoverage = 0;
uint32_t visualStartedAtMs = 0;
uint32_t visualTimeMs = 0;

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
static_assert(kLogoLayerCount * kRevealLayerMs + kTextFadeMs < kRevealDeadlineMs &&
                  kRevealDeadlineMs < 2000,
              "boot reveal must finish within two seconds");

bool elapsedAtLeast(uint32_t start, uint32_t duration) {
  return static_cast<uint32_t>(millis() - start) >= duration;
}

bool validateVideoApi(const t5_video_api_v1* api) {
  return api != nullptr && api->api_version == T5_VIDEO_API_VERSION &&
         api->struct_size >= sizeof(t5_video_api_v1) && api->start != nullptr &&
         api->backbuffer != nullptr && api->can_submit != nullptr &&
         api->submit != nullptr && api->pending != nullptr &&
         api->frame_counter != nullptr && api->stop != nullptr;
}

bool validateVideoSurface(const t5_video_surface_v1& surface) {
  if (surface.pixel_format != T5_VIDEO_PIXEL_MONO_1BPP_MSB) {
    return false;
  }
  if (surface.width < static_cast<uint16_t>(kFrameHeight) ||
      surface.height < static_cast<uint16_t>(kLogoSize)) {
    return false;
  }
  return surface.stride_bytes >= static_cast<uint16_t>((surface.width + 7U) / 8U);
}

uint8_t whiteByte() {
  return (videoSurface.flags & T5_VIDEO_FLAG_ONE_IS_BLACK) != 0U ? 0x00U : 0xFFU;
}

void setPhysicalPixel(uint8_t* buffer, size_t bufferSize, int logicalX,
                      int logicalY, bool black) {
  if (buffer == nullptr || logicalX < 0 || logicalY < 0 ||
      logicalX >= static_cast<int>(videoSurface.height) ||
      logicalY >= static_cast<int>(videoSurface.width)) {
    return;
  }

  // The fast-video surface is physical landscape. RiscRTE's boot artwork is
  // authored in portrait coordinates: logical (x,y) -> panel (y, H-1-x).
  const int panelX = logicalY;
  const int panelY = static_cast<int>(videoSurface.height) - 1 - logicalX;
  const size_t offset = static_cast<size_t>(panelY) * videoSurface.stride_bytes +
                        static_cast<size_t>(panelX >> 3);
  if (offset >= bufferSize) {
    return;
  }

  const uint8_t mask = static_cast<uint8_t>(0x80U >> (panelX & 7));
  const bool oneIsBlack =
      (videoSurface.flags & T5_VIDEO_FLAG_ONE_IS_BLACK) != 0U;
  const bool setBit = black == oneIsBlack;
  if (setBit) {
    buffer[offset] |= mask;
  } else {
    buffer[offset] &= static_cast<uint8_t>(~mask);
  }
}

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

const uint8_t* glyphFor(char ch) {
  static constexpr uint8_t blank[5] = {0, 0, 0, 0, 0};
  static constexpr uint8_t letters[26][5] = {
      {0x7E, 0x09, 0x09, 0x09, 0x7E},
      {0x7F, 0x49, 0x49, 0x49, 0x36},
      {0x3E, 0x41, 0x41, 0x41, 0x22},
      {0x7F, 0x41, 0x41, 0x22, 0x1C},
      {0x7F, 0x49, 0x49, 0x49, 0x41},
      {0x7F, 0x09, 0x09, 0x09, 0x01},
      {0x3E, 0x41, 0x49, 0x49, 0x7A},
      {0x7F, 0x08, 0x08, 0x08, 0x7F},
      {0x00, 0x41, 0x7F, 0x41, 0x00},
      {0x20, 0x40, 0x41, 0x3F, 0x01},
      {0x7F, 0x08, 0x14, 0x22, 0x41},
      {0x7F, 0x40, 0x40, 0x40, 0x40},
      {0x7F, 0x02, 0x0C, 0x02, 0x7F},
      {0x7F, 0x04, 0x08, 0x10, 0x7F},
      {0x3E, 0x41, 0x41, 0x41, 0x3E},
      {0x7F, 0x09, 0x09, 0x09, 0x06},
      {0x3E, 0x41, 0x51, 0x21, 0x5E},
      {0x7F, 0x09, 0x19, 0x29, 0x46},
      {0x26, 0x49, 0x49, 0x49, 0x32},
      {0x01, 0x01, 0x7F, 0x01, 0x01},
      {0x3F, 0x40, 0x40, 0x40, 0x3F},
      {0x1F, 0x20, 0x40, 0x20, 0x1F},
      {0x7F, 0x20, 0x18, 0x20, 0x7F},
      {0x63, 0x14, 0x08, 0x14, 0x63},
      {0x03, 0x04, 0x78, 0x04, 0x03},
      {0x61, 0x51, 0x49, 0x45, 0x43},
  };
  static constexpr uint8_t dot[5] = {0, 0x60, 0x60, 0, 0};

  if (ch >= 'a' && ch <= 'z') {
    ch = static_cast<char>(ch - ('a' - 'A'));
  }
  if (ch >= 'A' && ch <= 'Z') {
    return letters[ch - 'A'];
  }
  if (ch == '.') {
    return dot;
  }
  return blank;
}

void drawDitheredText(uint8_t* buffer, size_t bufferSize, int x, int y,
                      const char* text, int scale, uint8_t coverage) {
  if (text == nullptr || scale <= 0) {
    return;
  }

  for (const char* p = text; *p != '\0'; ++p) {
    const uint8_t* glyph = glyphFor(*p);
    for (int column = 0; column < 5; ++column) {
      for (int row = 0; row < 7; ++row) {
        if ((glyph[column] & (1U << row)) == 0U) {
          continue;
        }
        for (int sy = 0; sy < scale; ++sy) {
          for (int sx = 0; sx < scale; ++sx) {
            const int screenX = x + column * scale + sx;
            const int screenY = y + row * scale + sy;
            if (ditherPixel(screenX, screenY, coverage)) {
              setPhysicalPixel(buffer, bufferSize, screenX, screenY, true);
            }
          }
        }
      }
    }
    x += 6 * scale;
  }
}

int textWidth(const char* text, int scale) {
  if (text == nullptr || text[0] == '\0') {
    return 0;
  }
  return static_cast<int>((std::strlen(text) * 6U - 1U) *
                          static_cast<size_t>(scale));
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

bool waitUntilVideoCanSubmit(uint32_t timeoutMs, bool cancellable) {
  const uint32_t start = millis();
  while (videoApi != nullptr && !videoApi->can_submit()) {
    if ((cancellable && pulseStopRequested.load(std::memory_order_relaxed)) ||
        elapsedAtLeast(start, timeoutMs)) {
      return false;
    }
    delay(1);
  }
  return videoApi != nullptr &&
      !(cancellable && pulseStopRequested.load(std::memory_order_relaxed));
}

bool submitVideoFrame(uint8_t visibleBlocks, uint8_t logoCoverage,
                      uint8_t textCoverage,
                      uint32_t submitTimeoutMs = kSubmitTimeoutMs, bool cancellable = true) {
  if (!videoStarted || videoApi == nullptr ||
      !waitUntilVideoCanSubmit(submitTimeoutMs, cancellable)) {
    return false;
  }

  size_t bufferSize = 0;
  uint8_t* buffer = videoApi->backbuffer(&bufferSize);
  const size_t requiredSize =
      static_cast<size_t>(videoSurface.stride_bytes) * videoSurface.height;
  if (buffer == nullptr || bufferSize < requiredSize) {
    return false;
  }

  if (cancellable) visualTimeMs=static_cast<uint32_t>(millis()-visualStartedAtMs);
  std::memset(buffer, whiteByte(), bufferSize);
  drawVideoLogo(buffer, bufferSize, visibleBlocks, logoCoverage, textCoverage);
  return videoApi->submit(0, 0);
}

void waitForVideoIdle(uint32_t timeoutMs) {
  if (videoApi == nullptr) {
    return;
  }
  const uint32_t start = millis();
  while (videoApi->pending() && !elapsedAtLeast(start, timeoutMs)) {
    delay(1);
  }
}

bool releaseVideoOwner() {
  if (videoStarted && videoApi != nullptr) {
    videoApi->stop();
    videoStarted = false;  // A failed ownership restore must not reuse stopped video.
  }
  if (videoTakeoverActive) {
    const esp_err_t rc = native_hardware_takeover_end(
        T5_HARDWARE_TAKEOVER_DISPLAY | T5_HARDWARE_TAKEOVER_UI_VIDEO);
    if (rc != ESP_OK) {
      ESP_LOGE(kBootVideoTag, "display takeover release failed: %s", esp_err_to_name(rc));
      return false;  // Keep ownership/state for a safe retry; no overlapping owner.
    }
  }
  videoStarted = false;
  videoApi = nullptr;
  videoSurface = {};
  videoTakeoverActive = false;
  return true;
}

uint8_t smoothCoverage(uint8_t frame, uint8_t frameCount,
                       uint8_t startCoverage, uint8_t endCoverage) {
  const uint32_t t =
      static_cast<uint32_t>(frame) * 1024U / static_cast<uint32_t>(frameCount);
  const uint32_t smooth =
      static_cast<uint32_t>((static_cast<uint64_t>(t) * t *
                             (3072U - 2U * t)) /
                            (1024ULL * 1024ULL));
  return static_cast<uint8_t>(
      startCoverage +
      (static_cast<uint32_t>(endCoverage - startCoverage) * smooth) / 1024U);
}

bool renderLayerReveal();

void pulseTask(void*) {
  // Reveal and pulse both run alongside startup. Neither holds RenderLock,
  // accesses the renderer, scans SD, nor loads provider modules.
  const bool revealed = renderLayerReveal();
  uint8_t phase = static_cast<uint8_t>(kPulseFrames / 2U - 1U);
  while (revealed && !pulseStopRequested.load(std::memory_order_relaxed)) {
    const uint8_t ramp = phase < (kPulseFrames / 2U)
                             ? phase
                             : static_cast<uint8_t>(kPulseFrames - 1U - phase);
    const uint8_t coverage =
        smoothCoverage(ramp, static_cast<uint8_t>(kPulseFrames / 2U - 1U),
                       kPulseMinCoverage, kPulseMaxCoverage);
    if (submitVideoFrame(kLogoBlockCount, coverage, kFullCoverage)) {
      lastVisibleBlocks = kLogoBlockCount;
      lastPulseCoverage = coverage;
      lastTextCoverage = kFullCoverage;
      phase = static_cast<uint8_t>((phase + 1U) % kPulseFrames);
    }
    delay(35);  // Cap cosmetic work so real startup keeps the CPU.
  }
  pulseExited.store(true, std::memory_order_release);
  vTaskDelete(nullptr);  // No video/shared-state access after publishing exit.
}

bool startPulseTask() {
  pulseStopRequested.store(false, std::memory_order_relaxed);
  pulseExited.store(false, std::memory_order_relaxed);
  visualStartedAtMs = millis();
  visualTimeMs = 0;
  lastVisibleBlocks = 0;
  lastPulseCoverage = kFullCoverage;
  lastTextCoverage = 0;
  const BaseType_t rc = xTaskCreatePinnedToCore(
      pulseTask, "boot_animation", 4096, nullptr, 1, &pulseTaskHandle, 0);
  if (rc != pdPASS) {
    pulseTaskHandle = nullptr;
    pulseExited.store(true, std::memory_order_release);
  }
  return rc == pdPASS;
}

bool stopPulseTask() {
  pulseStopRequested.store(true, std::memory_order_relaxed);
  const uint32_t start = millis();
  while (!pulseExited.load(std::memory_order_acquire) && !elapsedAtLeast(start, 1000U)) delay(1);
  if (!pulseExited.load(std::memory_order_acquire)) {
    ESP_LOGW(kBootVideoTag, "animation still stopping; retaining video owner for retry");
    return false;  // Never delete a task inside driver code or free its buffers.
  }
  pulseTaskHandle = nullptr;
  return true;
}

bool waitForRevealTime(uint32_t start, uint32_t due) {
  while (!elapsedAtLeast(start, due)) {
    if (pulseStopRequested.load(std::memory_order_relaxed)) return false;
    delay(1);
  }
  return !pulseStopRequested.load(std::memory_order_relaxed);
}

bool renderLayerReveal() {
  // Preserve the left-to-right block build; animate the light field between
  // block arrivals rather than pausing the image at each discrete layer.
  const uint32_t start=millis();
  constexpr uint32_t duration=kLogoLayerCount*kRevealLayerMs+kTextFadeMs;
  uint32_t elapsed=0;
  do {
    if (pulseStopRequested.load(std::memory_order_relaxed)) return false;
    elapsed=static_cast<uint32_t>(millis()-start);
    if (elapsed>=kRevealDeadlineMs) return false;
    uint8_t visible=0, firstBlock=0;
    for (uint8_t layer=0; layer<kLogoLayerCount; ++layer) {
      const uint8_t lastBlock=kLogoLayerEnds[layer];
      const uint8_t blocksInLayer=lastBlock-firstBlock;
      for (uint8_t block=firstBlock+1; block<=lastBlock; ++block) {
        const uint32_t due=layer*kRevealLayerMs+(block-firstBlock)*kRevealLayerMs/blocksInLayer;
        if (elapsed>=due) visible=block;
      }
      firstBlock=lastBlock;
    }
    const uint32_t textElapsed=elapsed>kLogoLayerCount*kRevealLayerMs ? elapsed-kLogoLayerCount*kRevealLayerMs : 0;
    const uint8_t textFrame=static_cast<uint8_t>(textElapsed>=kTextFadeMs ? kTextFadeFrames : textElapsed*kTextFadeFrames/kTextFadeMs);
    const uint8_t textCoverage=smoothCoverage(textFrame,kTextFadeFrames,0,kFullCoverage);
    const uint32_t left=kRevealDeadlineMs-elapsed;
    if (!submitVideoFrame(visible,kFullCoverage,textCoverage,left<kSubmitTimeoutMs?left:kSubmitTimeoutMs)) return false;
    lastVisibleBlocks=visible;
    lastPulseCoverage=kFullCoverage;
    lastTextCoverage=textCoverage;
    if (elapsed<duration && !waitForRevealTime(start,elapsed+40u)) return false;
  } while (elapsed<duration);
  return true;
}

bool bootWithVideo(GfxRenderer& renderer) {
  (void)renderer;  // Keep the retained panel image until the spatial scrub.
  const esp_err_t takeoverRc =
      native_hardware_takeover_begin(T5_HARDWARE_TAKEOVER_DISPLAY | T5_HARDWARE_TAKEOVER_UI_VIDEO);
  if (takeoverRc != ESP_OK) {
    ESP_LOGW(kBootVideoTag, "display takeover unavailable: %s",
             esp_err_to_name(takeoverRc));
    return false;
  }
  videoTakeoverActive = true;
  bootBackend = BootBackend::Video;

  videoApi = t5_video_get_api(T5_VIDEO_API_VERSION);
  if (!validateVideoApi(videoApi) || !videoApi->start(&videoSurface)) {
    ESP_LOGE(kBootVideoTag, "EPD video service did not start");
    return !releaseVideoOwner();
  }
  videoStarted = true;

  if (!validateVideoSurface(videoSurface)) {
    ESP_LOGE(kBootVideoTag,
             "unsupported video surface %ux%u stride=%u format=%u",
             videoSurface.width, videoSurface.height,
             videoSurface.stride_bytes, videoSurface.pixel_format);
    return !releaseVideoOwner();
  }

  if (!startPulseTask()) {
    ESP_LOGE(kBootVideoTag, "boot animation worker unavailable");
    return !releaseVideoOwner();
  }

  bootBackend = BootBackend::Video;
  return true;
}

bool finishVideoBoot(GfxRenderer& renderer) {
  if (!stopPulseTask()) return false;
  // Readiness cancels even a partly drawn reveal. Fade only what was actually
  // submitted, with a total deadline; never finish the sequence just for show.
  const uint32_t start = millis();
  if (videoStarted && lastVisibleBlocks) {
    for (uint8_t frame = 1; frame <= kFadeFrames; ++frame) {
      const uint32_t elapsed = static_cast<uint32_t>(millis() - start);
      if (elapsed >= kReadyFadeBudgetMs) break;
      const uint32_t remaining = kFadeFrames - frame;
      const uint8_t coverage = lastPulseCoverage * remaining * remaining / (kFadeFrames * kFadeFrames);
      const uint8_t textCoverage = lastTextCoverage * remaining * remaining / (kFadeFrames * kFadeFrames);
      if (!submitVideoFrame(lastVisibleBlocks, coverage, textCoverage, kReadyFadeBudgetMs - elapsed, false)) break;
    }
  }
  // Always finish on known white, even when readiness interrupts the reveal.
  // Preserve that state across M5GFX re-init; otherwise handoff flashes again.
  bool whiteSettled = false;
  if (videoStarted && submitVideoFrame(0, 0, 0, kSubmitTimeoutMs, false)) {
    waitForVideoIdle(kIdleTimeoutMs);
    whiteSettled = !videoApi->pending();
  }
  if (!releaseVideoOwner()) return false;
  if (whiteSettled) display.suppressInitialFullRefresh();
  renderer.requestNextRefresh(whiteSettled ? DisplayPresentMode::LowLatency : DisplayPresentMode::Clean);
  return true;
}

#endif

}  // namespace

void boot(GfxRenderer& renderer) {
  loading.store(true, std::memory_order_release);
  fadePending = false;
  bootBackend = BootBackend::None;

#if defined(BOARD_T5S3_PRO) || defined(BOARD_T5S3)
  if (bootWithVideo(renderer)) {
    fadePending = true;
    return;
  }
#endif

  bootWithRenderer(renderer);
  fadePending = true;
}

void armBootFade() {
  loading.store(true, std::memory_order_release);
  fadePending = true;
}

bool isLoading() { return loading.load(std::memory_order_acquire); }

void destinationReady() {
  if (!isLoading() || fadePending) return;
  nativeTouchDiscardGestures();
  loading.store(false, std::memory_order_release);
}

bool finishBoot(GfxRenderer& renderer) {
  if (!fadePending) return true;

#if defined(BOARD_T5S3_PRO) || defined(BOARD_T5S3)
  if (bootBackend == BootBackend::Video) {
    if (!finishVideoBoot(renderer)) return false;
    bootBackend = BootBackend::None;
    fadePending = false;
    return true;
  }
#endif

  if (bootBackend == BootBackend::Renderer) {
    renderer.requestNextRefresh(DisplayPresentMode::Quality);
  }
  bootBackend = BootBackend::None;
  fadePending = false;
  return true;
}

}  // namespace StartupScreen
