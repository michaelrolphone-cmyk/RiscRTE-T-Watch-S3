# Read-only rollback corpus

Copyright Espressif Systems. ESP-IDF bootloader, Apache License2.0 (included).
This is the exact15104-byte native-USB Runtime0.1.10 CI bootloader, source
abef681d6c9c2b58729909a9961118ea20feee5e, run37197492618, artifact11301895269.
SHA256:2a71d69b471e20c2bac7fb469f3c6a807b3ebee780e348e5889db0da849ca363.

Its executable segments match the Arduino-ESP32 2.0.17 upstream SDK bootloader:
https://github.com/espressif/arduino-esp32/blob/2.0.17/tools/sdk/esp32s3/bin/bootloader_qio_80m.elf
Upstream ELF SHA256:560840d6c79821041dba7ce7a9a3a4fb98bc196b9017d66f9d4bc63f6da3a4c3.
Source rollback implementation:
https://github.com/espressif/esp-idf/blob/v4.4.7/components/bootloader_support/src/bootloader_utility.c

Base64 encoding is only a text-safe representation. No executable bytes were
modified. Tests copy it into fake flash and inspect its hash. They never execute,
install or flash this corpus. Production delivery must use the current exact
hosted paired Runtime artifact and independently audit it; this fixture is not a
replacement for native build provenance or physical bootloader qualification.
