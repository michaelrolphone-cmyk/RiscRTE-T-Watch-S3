# Native successor of the released watch-native-ui profile, Runtime4107.
# Product providers retain physical display, touch, power and board selection.
set(RISC_NATIVE_TARGET "esp32s3-16mb-appdata-expanded-iq")
set(RISC_NATIVE_PARTITIONS "${RISC_RUNTIME_ROOT}/partitions-paired-appdata-expanded.csv")
set(RISC_NATIVE_APPDATA ON)
set(RISC_NATIVE_IQ ON)
set(RISC_NATIVE_DEFINITIONS
    RISC_RUNTIME_PREFERENCE_STORE=1
    RISC_RUNTIME_STORAGE_FILES=1
    RISC_PAIRED_BANKS=1
    RISC_PAIRED_APP_DATA=1
    RISC_ENABLE_HTTP=1
    RISC_ENABLE_RADIO_IQ=1
    RISC_NATIVE_TCP_LISTENER=1
    RISC_NATIVE_ENTROPY=1
    RISC_INSTALLED_APP_CAPACITY=64
    RISC_NATIVE_RECOVERY_AXP2101=1
    RISC_RECOVERY_I2C_PORT=0
    RISC_RECOVERY_SDA=10
    RISC_RECOVERY_SCL=11
    RISC_STAGE_LOGS=1
    RISC_PERFORMANCE_TRACE=1
    RISC_NATIVE_FILE_SOURCE=1
    RISC_NATIVE_APP_DATA_MOUNT=1
    RISC_PAIRED_APP_DATA_EXPANDED=1
    RISC_PROVIDER_CAPACITY=40
    RISC_APP_POLICY_ROWS=32
    RISC_APP_REQUIREMENT_ROWS=32
    RISC_PERFORMANCE_TRACE_CAPACITY=64)
set(RISC_NATIVE_LINK_OPTIONS
    "-Wl,-u,risc_paired_store_abi"
    "-Wl,-u,risc_runtime_update_version"
    "-Wl,-u,risc_tcp_listener_abi"
    "-Wl,-u,risc_entropy_abi"
    "-Wl,-u,risc_file_source_abi"
    "-Wl,-u,__wrap_esp_littlefs_format"
    "-Wl,-u,__wrap_esp_littlefs_format_partition")
