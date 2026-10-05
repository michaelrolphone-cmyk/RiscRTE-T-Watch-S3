# Watch BLE Scanner integration

BLE Scanner 0.1.0 is included in the current app inventory with its own
satellite-dish icon. It uses Bluetooth instance 16 and existing preferences
namespace 1; it receives no additional persistent namespace or LoRa authority.
The shared Nova adapter keeps nested header Back inside the app and stops the
radio session before alerts, quick controls, sleep and handoff.

Watch Bluetooth provider 0.3.0 adds an append-only exclusive host lease. Legacy
power/packet calls are refused while a scanner owns the controller. Release
resets and closes the host before restoring the prior enabled state; cleanup
failure retains the lease. The scanner performs only explicitly requested
passive advertising scans and does not resume automatically after wake.

Software evidence includes the provider contract suite, target ELF validation,
exact app grants and adapter flags, full store admission, and the owner's
parser/controller/real-renderer tests. Physical discovery and power restoration
remain pending. Results are bounded to the invocation and are not persisted.
