# Explicit LoRa model and band selection

Provider 0.3.0 preserves the existing radio.lora@2 table prefix and appends
profile_info/select_profile. Applications check struct_size before accessing
the suffix. Profile information is four uint32 fields: struct_size,
supported_profiles, selected_profile, reserved (zero). Choice0 is unset;
choices1–4 are SX1262 433/868/915 MHz and SX1280 2.4 GHz. A supported choice's
mask bit is 1<<(choice-1).

The fixed config-v1 profiles retain their initialization behavior. New
semtech,sx1262-sx1280-selectable hardware uses radio.lora config version2: an
unchanged tw_hw_lora_v1 prefix followed by an explicit allowed_profiles mask.
The mask must be nonzero and contain only the four known bits. The full
430 MHz–2.5 GHz envelope authorizes the selector; each actual choice narrows RF
configuration to its existing exact band. Pins and bus remain fixed and scoped.

Selectable admission and choice changes perform no initialization, probing or
transmission. Initialization waits until the app explicitly configures the
chosen radio for Listen/Send. An unset choice cannot configure or transmit.
Changing an initialized choice resets and releases its held resources before
recording the next choice. Failed cleanup preserves the old choice and retained
resources and denies further configure until cleanup succeeds. Cancel releases
selectable hardware, preserving the explicit choice for later use. Wake and
modal dismissal cannot restart operation.

The picker must explain that its choice must match the installed radio and
antenna: selecting a different band does not convert the hardware. No automatic
model inference or trial transmissions are provided. A legacy RF record does
not establish the physical model; the app must request an explicit choice.

Software tests exercise all choices, fixed v1 behavior, inert admission and
selection, typed prefix and size checks, unknown masks, RF bounds, failed switch
retention and claim/transfer/cleanup retry. Hardware and RF performance remain
unqualified. This source increment does not install a selectable board profile
or add an application to the current Watch store; those integrations follow
with their exact tested Runtime and app pins.
