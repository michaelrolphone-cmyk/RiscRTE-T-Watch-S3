#include "Catalog.h"
#include <cassert>
#include <fstream>
#include <iterator>
#include <string>
static bool cooperate(void*){return true;}
int main(int argc,char** argv) {
  assert(argc==3);std::ifstream file(argv[1]);assert(file);
  std::string bytes{std::istreambuf_iterator<char>(file),{}};
  WatchUpdate::Catalog c;const bool expected=std::string(argv[2])=="accept";
  const bool parsed=WatchUpdate::parse({bytes.data(),bytes.size()},true,c,cooperate,nullptr);
  assert(parsed==expected);
  if(expected) {
    assert(c.count==1 && c.rows[0].pairedCohort && c.rows[0].storeAbi==2);
    assert(!strcmp(c.rows[0].view.version,"1.0.6"));
    assert(!strcmp(c.rows[0].layout,"riscrte-paired-appdata-v2"));
    assert(c.cohort.store_size==0x510000 && c.rows[0].view.size==c.cohort.firmware_size+c.cohort.store_size);
  }
}
