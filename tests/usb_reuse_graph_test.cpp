// Host-only integration. The physical controller boundary is deliberately fake;
// every host/HID/keyboard/gamepad/text/navigation module and the graph are real.
#include "runtime/drivers/ProviderGraphV2.h"
#include "RiscUsbInterruptV1.h"
#include "RiscInputNavigationV1.h"
#include "RiscPlatformClockV1.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

using RuntimeProviders::GraphV2;
using RuntimeProviders::RequirementV2;
using RuntimeProviders::SpecV2;
static bool controllerIdle = true;
static bool eventFailure = false;
static unsigned eventCalls = 0, cleanupCalls = 0;
static uint64_t now = 100;
static int32_t nextEvent(void*, risc_usb_controller_event_v1*) {
  ++eventCalls;
  return eventFailure ? -1 : 0;
}
static bool configuration(void*, uint64_t, uint8_t*, size_t*, uint16_t*, uint16_t*) { return false; }
static bool claim(void*, uint64_t, uint8_t, uint8_t, uint64_t*) { return false; }
static bool release(void*, uint64_t) { return false; }
static int32_t control(void*, uint64_t, uint8_t, uint8_t, uint16_t, uint16_t,
                       uint8_t*, uint16_t, uint32_t) { return -1; }
static int32_t read(void*, uint64_t, uint8_t, uint8_t*, size_t, uint32_t) { return -1; }
static int32_t write(void*, uint64_t, uint8_t, const uint8_t*, size_t, uint32_t) { return -1; }
static bool quiesce(void*) { ++cleanupCalls; return controllerIdle; }
static const risc_usb_controller_interrupt_v1 controller = {
  {1, sizeof(controller), nullptr, nextEvent, configuration, claim, release,
   control, read, write, quiesce}, read};
static const risc_platform_clock_api_v1 clockApi = {
  1, sizeof(clockApi), nullptr,
  [](void*) -> uint64_t { return now; },
  [](void*, uint32_t ms) { assert(ms <= 5000); now += ms; }};

// Generated from the unchanged pinned Reader manifests by the test runner.
#include "usb_reuse_inputs.inc"

static void populate(GraphV2& graph, const char* root, bool omitHid = false) {
  for (const auto& source : sources) {
    if (omitHid && !std::strcmp(source.id, "usb-hid")) continue;
    RequirementV2 requirements[16]{};
    for (size_t i = 0; i < source.count; ++i) {
      requirements[i] = {source.requirements[i], 1};
      if (!std::strcmp(source.requirements[i], "usb.controller"))
        requirements[i].trustedApi = &controller;
      if (!std::strcmp(source.requirements[i], "platform.clock"))
        requirements[i].trustedApi = &clockApi;
    }
    const std::string path = std::string(root) + "/" + source.id + ".so";
    assert(graph.addVerified({source.id, path.c_str(), source.capability, 1,
                              requirements, source.count}));
  }
}

int main(int argc, char** argv) {
  assert(argc == 2);
  {
    GraphV2 missing;
    populate(missing, argv[1], true);
    assert(!missing.acquire("input.navigation", 1).slot);
    assert(missing.shutdown());
  }
  GraphV2 graph;
  populate(graph, argv[1]);
  assert(graph.moduleCount() == 7);
  assert(!graph.acquire("input.navigation", 2).slot);
  auto grant = graph.acquire("input.navigation", 1);
  if (!grant.slot) std::fprintf(stderr, "%s\n", graph.lastError());
  assert(grant.slot);
  const auto* nav = static_cast<const risc_input_navigation_api_v1*>(graph.interfaceFor(grant));
  assert(nav && nav->struct_size >= sizeof(*nav));
  for (unsigned i = 0; i < 32; ++i) {
    const auto before = eventCalls;
    risc_input_navigation_frame_v1 frame{};
    assert(nav->poll(nav->context, &frame));
    assert(!frame.buttons && !frame.pressed && !frame.released);
    assert(eventCalls - before <= 32); // Quiet endpoints must not spin.
    now += 5;
  }
  const risc_input_foreground_v1 text[] = {{"input.text", 1}};
  assert(nav->foreground(nav->context, text, 1));
  assert(nav->foreground(nav->context, nullptr, 0));
  assert(nav->reset(nav->context));
  auto host = graph.acquire("usb.host", 1);
  assert(host.slot && !graph.shutdown());
  assert(graph.release(grant));
  assert(!graph.interfaceFor(grant));
  assert(graph.interfaceFor(host)); // Shared dependency survives top-level exit.
  controllerIdle = false;
  assert(!graph.release(host));
  assert(!graph.interfaceFor(host)); // Revoke before the failed cleanup retry.
  assert(!graph.acquire("input.navigation", 1).slot);
  assert(cleanupCalls);
  controllerIdle = true;
  assert(graph.release(host));
  assert(graph.shutdown());
  auto fresh = graph.acquire("input.navigation", 1);
  assert(fresh.slot && fresh.generation != grant.generation);
  assert(!graph.interfaceFor(grant));
  assert(graph.release(fresh) && graph.shutdown());

  auto lastHost = graph.acquire("usb.host", 1);
  assert(lastHost.slot);
  const auto* api = static_cast<const risc_usb_host_snapshot_v1*>(graph.interfaceFor(lastHost));
  eventFailure = true;
  size_t count = RISC_USB_HOST_MAX_DEVICES;
  risc_usb_device_identity_v1 devices[RISC_USB_HOST_MAX_DEVICES]{};
  assert(!api->snapshot(api->discovery.host.context, devices, &count));
  eventFailure = false;
  assert(graph.release(lastHost) && graph.shutdown());
  std::puts("Pinned Reader input stack on minimal runtime graph: missing dependency, ABI refusal, quiet poll, foreground handoff, shared ownership, failed-quiesce retention, revocation, retry and fresh generation PASS");
}
