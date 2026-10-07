# Portable Spectrum integration

Upstream is libfvad commit532ab666c20d3cfda38bca63abbb0f152706c369.
The16kHz,20ms Gaussian-mixture detector is used with fixed storage. No neural
network, microphone upload, transcription or speaker identification is included.

Local changes: the model multiply uses explicit unsigned modulo arithmetic
instead of an undefined signed multiplication with a sanitizer exemption; the
lifetime frame counter saturates; Xtensa omits debug-only assertions because the
native app import contract has no assertion-abort API. Host assertions remain.
The three upstream48kHz resampler sanitizer annotations are retained; Spectrum
calls only the16kHz path. Source hashes and provenance are in SOURCES.json.
