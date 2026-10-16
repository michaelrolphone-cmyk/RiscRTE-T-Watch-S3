# Native SDK 6.1 Watch profile

`profiles/native-idf61.cmake` retains the released `watch-native-ui` selections
from Runtime `4107eaeedd8c801eeaf7deb1c7bc4a943cd27342`. Product 1.1.39
retained the native 1.1.37 bytes; its native SHA-256 is
`2af6900838b995cd19752c5b95a580f596902d2e49966388195f16db2c595099`.
The flattened legacy profile and immutable source identities are recorded in
`profiles/native-idf61-baseline.json`.

The new profile selects the same expanded paired partitions, IQ/HTTP/TCP,
entropy, AppData file source, application/provider capacities, recovery PMIC
pins, performance trace capacity and retained public ABI markers. Physical
display, touch and power remain selected by the product's provider graph.
The profile does not add a native settings backend to this product.

Configure a qualified migration Runtime checkout with the official pinned SDK
6.1 and its ESP32-S3 GCC15 toolchain:

```sh
cmake -S "$RUNTIME/idf" -B "$BUILD" -G Ninja \
  -DRISC_PRODUCT_PROFILE="$PWD/profiles/native-idf61.cmake"
cmake --build "$BUILD" -- -j1
python tests/test_native_idf61_profile.py --runtime "$RUNTIME"
```

The shared CMake build owns SDK configuration, all nine SDK6 AppData custody
wrappers, and the final IQ memory/ROM proof. A source-closed product build and
package qualification are required before release. This profile is a source
migration checkpoint, not a device-tested firmware release.
