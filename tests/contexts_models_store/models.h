#ifndef CONTEXTS_MODELS_STORE_MODELS_H
#define CONTEXTS_MODELS_STORE_MODELS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    CONTEXTS_MODELS_FIXTURE_AUDIO_NAMESPACE = 2,
    CONTEXTS_MODELS_FIXTURE_RADIO_NAMESPACE = 3
};

typedef struct contexts_models_fixture_info {
    uint32_t bank_generation[2];
    uint32_t bank_size[2];
    uint32_t bank_crc[2];
    uint32_t neural_size;
    uint32_t positive_examples;
    uint32_t negative_examples;
    uint32_t labels;
    /* First successful import into a freshly started Contexts service. */
    uint32_t initial_temporal_generation;
} contexts_models_fixture_info;

/* Train once using the canonical Utilities trainers, then encode both banks
 * and their promoted checkpoint. Returns false on any failed validation.
 * Compile models.c as C with Utilities Apps/ and tests/ on the include path. */
bool contexts_models_fixture_init(void);

/* Exact owner filename and namespace lookup. The returned immutable storage
 * survives for the process lifetime. Before initialization, or on an unknown
 * name/namespace, return NULL and set *size to zero. size may be NULL. */
const uint8_t *contexts_models_fixture_record(unsigned namespace_id,
                                            const char *owner_filename,
                                            size_t *size);

/* Returns false before initialization or for an invalid namespace/output. */
bool contexts_models_fixture_metadata(unsigned namespace_id,
                                      contexts_models_fixture_info *out);

#ifdef __cplusplus
}
#endif

#endif
