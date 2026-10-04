#!/usr/bin/env bash
set -euo pipefail
watch="$(cd "$(dirname "$0")/.." && pwd)"
runtime="$(cd "${1:?Pass exact Runtime source}" && pwd)"
utilities="$(cd "${2:?Pass exact Utilities source}" && pwd)"
# Reuse the reviewed Utilities target-layout harness against every final
# alarm-enabled app/service ELF and the actual selected Runtime relocator.
# Models target layout; does not execute Xtensa instructions on the host.
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
cc -std=gnu11 -O1 -g -I"$utilities/test/alarm-loader-stubs" -I"$runtime/lib/elf_loader/include" \
 "$utilities/test/alarm_target_loader.c" "$runtime/lib/elf_loader/src/esp_elf.c" \
 "$runtime/lib/elf_loader/src/arch/esp_elf_xtensa.c" "$runtime/lib/elf_loader/src/esp_elf_validate.c" \
 -o "$build/target-loader"
"$build/target-loader" "$watch"/dist/alarm-launcher/*.elf
