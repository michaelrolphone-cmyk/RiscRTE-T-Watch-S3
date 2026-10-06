#include "Catalog.h"
#include <cassert>
#include <fstream>
#include <iterator>
#include <string>
static bool cooperate(void*){return true;}
int main(int argc,char** argv){
 assert(argc==3);std::ifstream file(argv[1]);assert(file);std::string bytes{std::istreambuf_iterator<char>(file),{}};
 WatchUpdate::Catalog c;assert(WatchUpdate::parse({bytes.data(),bytes.size()},true,c,cooperate,nullptr));
 bool cohort=std::string(argv[2])=="cohort";assert(c.count==1 && c.rows[0].pairedCohort==cohort && c.rows[0].storeAbi==2);
 assert(!strcmp(c.rows[0].layout,"riscrte-paired-appdata-v2"));
 assert(!strcmp(c.rows[0].view.version,cohort?"1.0.4":"0.1.34"));
 if(cohort)assert(c.cohort.store_size==0x510000 && c.rows[0].view.size==c.cohort.firmware_size+c.cohort.store_size);
 assert(WatchUpdate::parse({bytes.data(),bytes.size()},false,c,cooperate,nullptr));
}
