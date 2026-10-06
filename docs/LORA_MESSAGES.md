# Watch LoRa Messages integration

LoRa Messages 0.1.1 uses the shared Nova UI, Points keyboard and 12/24-hour
preference. Its exclusive radio authority is radio.lora@2 instance 11; its
versioned 32-byte RF profile and explicit radio choice are in namespace 9.
Shared preferences remain namespace 1. There are no automatic transmissions or
RF defaults. Listen and Send are explicit actions; cancellation must succeed
before sleep, alerts or handoff.

The current builder defaults to the selectable radio profile. One firmware
supports SX1262 433/868/915 MHz and SX1280 2.4 GHz choices in the app. Admission
and selecting an idle radio perform no hardware initialization. The selection
must match the installed radio and antenna; the picker does not convert them.
A legacy RF record leaves the choice unset until the user selects it explicitly.
The source also retains fixed profiles for explicit software/qualification builds.

Runtime 0.1.29 materializes the typed bus, chip select, reset and no-pull BUSY/IRQ
inputs with an explicit allowed-profile mask. Watch driver 0.3.0 requests that
exact authority and initializes only when the app configures an operation after
Listen/Send. Failed cleanup retains the prior choice/resources and blocks new
configuration until cancellation succeeds. Physical send, receive, antenna
matching and power behavior remain unqualified.
