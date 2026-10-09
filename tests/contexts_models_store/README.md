# Contexts owner model import through Runtime

This host lane loads the actual Runtime/CpuPort/provider graph, Clock, and Audio
Spectrum/Waterfall owner modules. It leaves the production Watch source and
candidate store selected by `--watch` unchanged. The initial-image packager
requires this fixture and the production Watch source to be the same clean
checkout, so both are included in the candidate's source identity.

`models.c` uses the canonical Utilities libraries to make deterministic saved
models. Each source has two labels, three positives and two negatives per label,
two encoded banks at generations 3 and 5, and a checkpoint promoted by the
canonical trainer. Training occurs only in this fixture. The native storage
backend checks exact owner names, namespaces 2/3, filenames, revision and bounds.
No storage writes are permitted. The real service must report both temporal and
neural readiness, first import generation 1, exact bank sizes, six positives and
four negatives. PCM reads remain empty, so this lane claims no recognition.

Separate cases return true AppData RETAINED at each owner's first stat or read.
The actual Runtime must retain the active owner and provider mappings. Hardware,
storage, display and module counters must remain unchanged after the retained
boundary. The fixture does not resume a retained Runtime invocation. Focused
Utilities owner tests additionally inspect zero service finish/status/release
calls after RETAINED, and the later invocation's abandonment handling.

Run against an already built candidate, using its exact source pins:

```sh
SANITIZE=0 ADDRESS_SANITIZE=0 python scripts/test_contexts_model_runtime.py \
  --watch /path/to/production-watch --runtime /path/to/runtime \
  --system /path/to/system --utilities /path/to/utilities \
  --drivers /path/to/drivers --store /path/to/candidate/files \
  --output /path/to/new-normal-output
ASAN_OPTIONS=detect_leaks=0 SANITIZE=1 ADDRESS_SANITIZE=1 \
  python scripts/test_contexts_model_runtime.py [same inputs, new output]
```

The runner preserves the selected five-app LTO policy and section GC for the
source-compiled host app modules. Its separate schema-1 model proof binds the
candidate inventory, source pins, source hashes, fixture source and every case.
It cannot substitute for the four schema-2 enabled/disabled baseline reports;
the initial-image packager requires all six reports.
LeakSanitizer is disabled consistently with the repository's other host lanes;
address and undefined-behavior instrumentation remain active. No Xtensa
instructions or physical hardware are executed, and no image is assembled.
