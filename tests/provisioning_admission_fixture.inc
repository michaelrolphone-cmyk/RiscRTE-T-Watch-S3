 static const risc_provision_request_api_v1 request{1,sizeof(request),nullptr,
  [](void*,risc_provision_request_status_v1*)->int32_t{++storageCalls;return RISC_PROVISION_REQUEST_UNAVAILABLE;},
  [](void*,const risc_provision_request_v1*,uint8_t*)->int32_t{++storageCalls;return RISC_PROVISION_REQUEST_UNAVAILABLE;}};
 if(!runtime.registerPlatform(RISC_PROVISION_REQUEST_CAPABILITY,1,RiscBoot::Runtime::Scope::Global,0,&request))return false;
 static risc_storage_volume_api_v1_download download{};
 auto& v=*reinterpret_cast<risc_storage_volume_api_v1*>(&download);
 v.api_version=1;v.struct_size=sizeof(download);
 auto& state=download.base.base.fs.state;
 state.state_tag=RISC_STORAGE_STATE_TAG;state.state_version=1;
 state.observe=[](void*)->int32_t{++storageCalls;return RISC_STORAGE_STATE_UNAVAILABLE;};
 auto& fs=download.base.base.fs;
 fs.fs_tag=RISC_STORAGE_FS_TAG;fs.fs_version=1;
 fs.dir_tell=[](void*,risc_storage_dir_t,uint64_t*){++storageCalls;return false;};
 fs.dir_seek=[](void*,risc_storage_dir_t,uint64_t){++storageCalls;return false;};
 fs.metadata=[](void*,const char*,risc_storage_metadata_v1*)->int32_t{++storageCalls;return RISC_STORAGE_FS_IO;};
 fs.file_truncate=[](void*,risc_storage_file_t,uint64_t){++storageCalls;return false;};
 fs.replace_file=[](void*,const char*,const char*){++storageCalls;return false;};
 fs.recover_replace=[](void*,const char*){++storageCalls;return false;};
 auto& async=download.base.base;
 async.async_tag=RISC_STORAGE_ASYNC_TAG;async.async_version=RISC_STORAGE_ASYNC_VERSION;
 async.begin=[](void*,uint64_t*)->int32_t{++storageCalls;return RISC_STORAGE_ASYNC_IO;};
 async.submit=[](void*,uint64_t,const risc_storage_async_request_v1*,uint64_t*)->int32_t{++storageCalls;return RISC_STORAGE_ASYNC_IO;};
 async.collect=[](void*,uint64_t,uint64_t,risc_storage_async_result_v1*)->int32_t{++storageCalls;return RISC_STORAGE_ASYNC_IO;};
 async.end=[](void*,uint64_t)->int32_t{++storageCalls;return RISC_STORAGE_ASYNC_IO;};
 download.base.package_tag=RISC_STORAGE_PACKAGE_TAG;download.base.package_version=1;
 download.base.submit_package=[](void*,uint64_t,const risc_storage_package_request_v1*,uint64_t*)->int32_t{++storageCalls;return RISC_STORAGE_ASYNC_IO;};
 download.download_tag=RISC_STORAGE_DOWNLOAD_TAG;download.download_version=2;
 static const risc_internal_package_volume_v1 package{1,sizeof(package),nullptr,&v,[](void*){++storageCalls;return false;}};
 if(!runtime.registerPlatform(RISC_INTERNAL_PACKAGE_VOLUME_CAPABILITY,1,RiscBoot::Runtime::Scope::Global,0,&package))return false;

