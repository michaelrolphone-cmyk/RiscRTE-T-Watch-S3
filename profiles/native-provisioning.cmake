# Retain every released physical/serial selection, then explicitly enable the
# native package-volume and preserving next-boot request adapters.
include("${CMAKE_CURRENT_LIST_DIR}/native-idf61.cmake")
list(APPEND RISC_NATIVE_DEFINITIONS
    RISC_NATIVE_PACKAGE_VOLUME=1
    RISC_NATIVE_PROVISION_REQUEST=1
    RISC_PLATFORM_CAPACITY=32)
