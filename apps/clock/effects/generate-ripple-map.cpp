#include <cstdio>
#include <vector>
#include "reference/NativeVideoBootScrub.h"
int main(){using namespace NativeVideoBootScrub;std::vector<uint8_t> m(kMapBytes);for(unsigned y=0;y<kHeight;y+=kGrid)buildBand(m.data(),y);puts("/* Generated from the pinned T5 spatial waveform; portrait 240x240 sample. */\nstatic const uint8_t arrivals[240*240]={");for(unsigned y=0;y<240;y++){for(unsigned x=0;x<240;x++)printf("%u,",m[((239-x)*540/240)*960+y*960/240]);puts("");}puts("};");}
