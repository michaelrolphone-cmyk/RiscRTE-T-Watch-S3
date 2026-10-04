#pragma once

#include <cmath>
#include <cstddef>
#include <cstdint>

// Video-start spatial waveform, shared with the host preview. Commands are raw
// EPD drives: 0 = retain, 1 = black, 2 = white. Every pixel gets the same finite
// endpoint treatment, staggered along curling contours instead of global fills.
namespace NativeVideoBootScrub {
constexpr unsigned kWidth = 960, kHeight = 540;
constexpr unsigned kScans = 16, kLastArrival = 7;
constexpr unsigned kBlackScans = 3, kWhiteScans = 6;
constexpr unsigned kGrid = 4, kGridWidth = kWidth / kGrid + 1;
constexpr size_t kMapBytes = kWidth * kHeight;
static_assert(kLastArrival + kBlackScans + kWhiteScans == kScans, "complete all endpoints");

inline uint16_t field(unsigned x, unsigned y) {
  // Work in portrait coordinates. Two off-axis eddies and a warped phase make
  // broad ribbons curl into finer tips without a rigid centered pinwheel.
  const float u = (static_cast<float>(y) - 270.0f) / 360.0f;
  const float v = (960.0f - static_cast<float>(x) - 480.0f) / 360.0f;
  const float dx = u + 0.14f * std::sin(v * 3.2f);
  const float dy = v - 0.20f;
  const float r = std::sqrt(dx * dx + dy * dy);
  const float a = std::atan2(dy, dx);
  const float curl = 2.0f * a + 7.6f * r + 0.8f * std::sin(v * 3.0f + u * 2.0f);
  float t = 0.5f + 0.34f * std::sin(curl) + 0.12f * std::sin(a - r * 5.0f)
                    + 0.035f * std::sin(u * 8.0f + v * 3.0f);
  if (t < 0.0f) t = 0.0f;
  if (t > 1.0f) t = 1.0f;
  return static_cast<uint16_t>(t * (kLastArrival * 256.0f));
}

// Four scanlines per bounded unit. Trigonometry runs only at 4px grid vertices
// before panel scanning; the actual scan loop uses one byte lookup per pixel.
inline void buildBand(uint8_t* map, unsigned y) {
  uint16_t top[kGridWidth], bottom[kGridWidth];
  for (unsigned gx = 0; gx < kGridWidth; ++gx) {
    top[gx] = field(gx * kGrid, y);
    bottom[gx] = field(gx * kGrid, y + kGrid);
  }
  for (unsigned sy = 0; sy < kGrid && y + sy < kHeight; ++sy) {
    for (unsigned x = 0; x < kWidth; ++x) {
      const unsigned gx = x / kGrid, sx = x % kGrid;
      const unsigned l = top[gx] * (kGrid - sy) + bottom[gx] * sy;
      const unsigned r = top[gx + 1] * (kGrid - sy) + bottom[gx + 1] * sy;
      map[(y + sy) * kWidth + x] = static_cast<uint8_t>(
          (l * (kGrid - sx) + r * sx) / (kGrid * kGrid * 256));
    }
  }
}

inline uint8_t command(unsigned arrival, unsigned scan) {
  if (scan < arrival || scan >= arrival + kBlackScans + kWhiteScans) return 0;
  return scan < arrival + kBlackScans ? 1 : 2;
}

inline void driveRow(const uint8_t* map, unsigned y, unsigned scan, uint8_t* drive) {
  for (unsigned x = 0; x < kWidth; x += 4) {
    const uint8_t* p = map + y * kWidth + x;
    drive[x / 4] = static_cast<uint8_t>((command(p[0], scan) << 6) |
        (command(p[1], scan) << 4) | (command(p[2], scan) << 2) | command(p[3], scan));
  }
}
}  // namespace NativeVideoBootScrub
