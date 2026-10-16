# Watch18 compiler-input custody

The lifecycle builder retains the historical Contexts compiler and frozen
Watch18 artifacts. Its new `QualifiedCompiler` uses the same target commands,
but checks the compiler's own dependency closure before and after compilation.
Every non-system input must match its independently selected Git blob. The only
generated inputs are the two exact catalog sources. Linked inputs, host fixtures,
untracked or ignored shadow dependencies, and `.gch`/`.pch` inputs are refused.

The unchanged System builder still produces firmware provider 0.1.5. The Watch
wrapper checks its inputs before and after that build with the exact C++17,
exception, RTTI and feature flags, then admits only the expected build record.

`build.json` records the selected source roots and pins. `verify()` reconstructs
every application/provider dependency command, repeats source admission and
requires exact equality with the recorded dependencies. Select the trusted
target compiler independently with `TWATCH_CC` or the verifier's `cc` argument;
the verifier never executes a compiler path obtained from an artifact receipt.
Source checkouts and the two generated catalog files must remain available for
verification. This verifies software input custody, not hardware behavior.

Run the focused regressions with the build Python environment:

    python -m unittest discover -s tests -p test_lifecycle_source_custody.py -v

The tests invoke real host compilers and temporary Git repositories. They cover
ignored shadow headers, ignored valid precompiled headers, linked and changed
sources, generated-file changes, false dependency receipts and a C++17-specific
include that a C++11 scan would miss.
