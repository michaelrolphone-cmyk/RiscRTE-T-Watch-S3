// Parse prepared inputs through the selected provider grammar. Compatibility
// with the starting installed provider is separately reported by the builder.
#include "Catalog.h"
#include <cassert>
#include <fstream>
#include <iterator>
#include <string>
static std::string read(const char* path) {
 std::ifstream file(path);assert(file);return {std::istreambuf_iterator<char>(file),{}};
}
static bool cooperate(void*) {return true;}
int main(int argc,char** argv) {
 assert(argc==4);const auto json=read(argv[1]),previous=read(argv[2]);
 WatchUpdate::Catalog catalog;
 assert(WatchUpdate::parse({json.data(),json.size()},true,catalog,cooperate,nullptr));
 assert(catalog.count==1 && catalog.rows[0].storeAbi==2 && catalog.rows[0].pairedCohort);
 assert(catalog.cohort.struct_size==sizeof(catalog.cohort));
 assert(catalog.cohort.store_size==0x510000);
 assert(catalog.rows[0].view.size==catalog.cohort.firmware_size+catalog.cohort.store_size);
 assert(!std::strcmp(catalog.rows[0].layout,"riscrte-paired-appdata-v2"));
 assert(!std::strcmp(catalog.rows[0].view.version,argv[3]));
 assert(WatchUpdate::parse({json.data(),json.size()},false,catalog,cooperate,nullptr));
 bool found=false;
 for(unsigned i=0;i<catalog.count;++i) {
  auto& row=catalog.rows[i];if(std::strcmp(row.view.id,"audio_spectrum"))continue;
  WatchUpdate::WorkBudget budget(cooperate,nullptr);
  WatchUpdate::Manifest before,after;
  assert(WatchUpdate::manifest({previous.data(),previous.size()},"audio_spectrum",before,budget));
  assert(WatchUpdate::manifest(row.manifest,"audio_spectrum",after,budget));
  assert(WatchUpdate::authority(before,after));found=true;
 }
 assert(found);
}
