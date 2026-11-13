# Preserve the complete selected provisioning profile; increase provider rows only.
include("${CMAKE_CURRENT_LIST_DIR}/native-provisioning.cmake")
list(REMOVE_ITEM RISC_NATIVE_DEFINITIONS RISC_PROVIDER_CAPACITY=40)
list(APPEND RISC_NATIVE_DEFINITIONS RISC_PROVIDER_CAPACITY=48)
