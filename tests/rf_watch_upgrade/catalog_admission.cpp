// Read only the supplied synthetic framing fixture through the exact installed
// provider's production catalog parser. No download, publication or device I/O.
#include "Catalog.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>

static bool cooperate(void*) { return true; }

int main(int argc,char** argv) {
  if(argc!=2)return 2;
  std::ifstream input(argv[1],std::ios::binary);if(!input)return 2;
  const std::string bytes{std::istreambuf_iterator<char>(input),{}};
  WatchUpdate::Catalog catalog;
  const bool parsed=WatchUpdate::parse({bytes.data(),bytes.size()},true,catalog,cooperate,nullptr);
  std::cout<<"{\"accepted\":"<<(parsed?"true":"false")<<",\"row_count\":"<<catalog.count;
  if(parsed && catalog.count==1) {
    const auto& row=catalog.rows[0];
    std::cout<<",\"paired_cohort\":"<<(row.pairedCohort?"true":"false")
      <<",\"store_abi\":"<<row.storeAbi<<",\"firmware_size\":"<<catalog.cohort.firmware_size
      <<",\"store_size\":"<<catalog.cohort.store_size<<",\"payload_size\":"<<row.view.size;
  }
  std::cout<<"}\n";
}
