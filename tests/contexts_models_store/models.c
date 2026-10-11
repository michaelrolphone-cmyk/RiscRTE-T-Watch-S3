/* Test-only saved-model generator. All model training, promotion, validation,
 * and encoding use the canonical Utilities implementation. */
#include "models.h"
#include <stdio.h>
#include <string.h>

#include "spectrum_temporal_store.h"
#include "spectrum_neural_store.h"
#include "spectrum_neural_fixture.h"
#include "rf_temporal_store.h"
#include "rf_neural_store.h"

static st_library audio_library;
static rt_library radio_library;
static sn_trainer audio_trainer;
static rn_trainer radio_trainer;
static uint8_t audio_banks[2][ST_BANK_MAX];
static uint8_t radio_banks[2][RT_BANK_MAX];
static uint8_t audio_checkpoint[SN_RECORD_SIZE];
static uint8_t radio_checkpoint[RN_RECORD_SIZE];
static contexts_models_fixture_info fixture_info[2];
static bool initialized;

/* Canonical RF test recordings from rf_temporal_model_test.c: sparse observed
 * frames, the same ambiguous decays, and explicitly taught confusing negatives.
 * This generates observations only; it does not duplicate trainer logic. */
static rt_example radio_example(unsigned identity, unsigned recording,
                                unsigned kind)
{
    rt_segmenter segment = {0};
    uint32_t power[128] = {0}, previous[128] = {0}, now = 1000;
    const unsigned envelope[] = {100, 70, 48, 31, 21, 11, 5, 1};

    for (unsigned i = 0; i < 4; ++i) {
        rt_frame frame = rt_frame_make(power, previous, false, now, true);
        now += 100;
        rt_segment_observe(&segment, &frame);
    }
    for (unsigned i = 0; i < 8; ++i) {
        unsigned amplitude = (envelope[i] + (recording == 2 && i > 0)) *
                             (10 + recording);
        memset(power, 0, sizeof(power));
        power[15] = amplitude * 10000;
        power[18] = amplitude * 8000;
        if (i == 2 && identity < 2)
            power[identity ? 40 : 30] = amplitude * 8000;
        if (i == 2 && identity == 2)
            power[30] = power[40] = amplitude * 4000;
        rt_frame frame = rt_frame_make(power, previous, true, now, true);
        now += 100;
        rt_segment_observe(&segment, &frame);
        memcpy(previous, power, sizeof(power));
    }
    for (unsigned i = 0; i < 4; ++i) {
        memset(power, 0, sizeof(power));
        rt_frame frame = rt_frame_make(power, previous, false, now, true);
        now += 100;
        rt_segment_observe(&segment, &frame);
        memcpy(previous, power, sizeof(power));
    }
    segment.event.id = recording + 1;
    segment.event.kind = (uint8_t)kind;
    return segment.event;
}

static bool prepare_libraries(void)
{
    memset(&audio_library, 0, sizeof(audio_library));
    memset(&radio_library, 0, sizeof(radio_library));
    audio_library.generation[0] = radio_library.generation[0] = 3;
    audio_library.generation[1] = radio_library.generation[1] = 5;
    radio_library.identity = rf_identity_default();

    for (unsigned i = 0; i < 2; ++i) {
        st_label *audio = &audio_library.labels[i];
        rt_label *radio = &radio_library.labels[i];
        audio->present = radio->present = true;
        audio->next_id = radio->next_id = 6;
        snprintf(audio->name, sizeof(audio->name), "Sound %u", i);
        snprintf(radio->name, sizeof(radio->name), "RF label %u", i);
        for (unsigned j = 0; j < 5; ++j) {
            unsigned identity = j < 3 ? i : 2;
            audio->examples[j] = sn_fixture_example(identity, j,
                                                   j < 3 ? ST_POSITIVE : ST_NEGATIVE);
            radio->examples[j] = radio_example(identity, j,
                                               j < 3 ? RT_POSITIVE : RT_NEGATIVE);
        }
        if (!st_label_valid(audio) || !rt_label_valid(radio))
            return false;
    }
    return true;
}

static bool train_models(void)
{
    sn_reset(&audio_trainer, &audio_library, 255);
    unsigned ticks = 0;
    while (audio_trainer.state >= SN_PREPARING &&
           audio_trainer.state <= SN_CHECKING) {
        if (++ticks > 4000)
            return false;
        sn_tick(&audio_trainer, &audio_library);
    }
    rn_reset(&radio_trainer, &radio_library, 255);
    ticks = 0;
    while (radio_trainer.state >= RN_PREPARING &&
           radio_trainer.state <= RN_CHECKING) {
        if (++ticks > 4000)
            return false;
        rn_tick(&radio_trainer, &radio_library);
    }
    return audio_trainer.has_active && audio_trainer.state == SN_ACTIVE &&
           radio_trainer.has_active && radio_trainer.state == RN_ACTIVE;
}

bool contexts_models_fixture_init(void)
{
    if (initialized)
        return true;
    memset(fixture_info, 0, sizeof(fixture_info));
    if (!prepare_libraries() || !train_models())
        return false;

    for (unsigned bank = 0; bank < 2; ++bank) {
        size_t audio_size = st_bank_encode(&audio_library, bank, audio_banks[bank],
                                          sizeof(audio_banks[bank]));
        size_t radio_size = rt_bank_encode(&radio_library, bank, radio_banks[bank],
                                          sizeof(radio_banks[bank]));
        if (!audio_size || !radio_size)
            return false;
        fixture_info[0].bank_size[bank] = (uint32_t)audio_size;
        fixture_info[1].bank_size[bank] = (uint32_t)radio_size;
        fixture_info[0].bank_generation[bank] = audio_library.generation[bank];
        fixture_info[1].bank_generation[bank] = radio_library.generation[bank];
        fixture_info[0].bank_crc[bank] =
            spectrum_signature_u32(audio_banks[bank] + audio_size - 4);
        fixture_info[1].bank_crc[bank] =
            rf_signature_u32(radio_banks[bank] + radio_size - 4);
    }
    if (!sn_record_encode(&audio_trainer, &audio_library, fixture_info[0].bank_crc,
                          audio_checkpoint, sizeof(audio_checkpoint)) ||
        !rn_record_encode(&radio_trainer, &radio_library, fixture_info[1].bank_crc,
                          radio_checkpoint, sizeof(radio_checkpoint)))
        return false;

    fixture_info[0].neural_size = SN_RECORD_SIZE;
    fixture_info[1].neural_size = RN_RECORD_SIZE;
    for (unsigned slot = 0; slot < ST_LABELS; ++slot) {
        fixture_info[0].labels += audio_library.labels[slot].present;
        fixture_info[1].labels += radio_library.labels[slot].present;
        fixture_info[0].positive_examples +=
            st_example_count(&audio_library.labels[slot], ST_POSITIVE);
        fixture_info[0].negative_examples +=
            st_example_count(&audio_library.labels[slot], ST_NEGATIVE);
        fixture_info[1].positive_examples +=
            rt_example_count(&radio_library.labels[slot], RT_POSITIVE);
        fixture_info[1].negative_examples +=
            rt_example_count(&radio_library.labels[slot], RT_NEGATIVE);
    }
    fixture_info[0].initial_temporal_generation = 1;
    fixture_info[1].initial_temporal_generation = 1;
    initialized = true;
    return true;
}

static int source_index(unsigned namespace_id)
{
    if (namespace_id == CONTEXTS_MODELS_FIXTURE_AUDIO_NAMESPACE)
        return 0;
    if (namespace_id == CONTEXTS_MODELS_FIXTURE_RADIO_NAMESPACE)
        return 1;
    return -1;
}

const uint8_t *contexts_models_fixture_record(unsigned namespace_id,
                                            const char *owner_filename,
                                            size_t *size)
{
    static const char *const names[2][3] = {
        {"spectrum-events-a.sqt", "spectrum-events-b.sqt", "spectrum-neural.snn"},
        {"rf-events-a.rft", "rf-events-b.rft", "rf-neural.rnn"}
    };
    if (size)
        *size = 0;
    int source = source_index(namespace_id);
    if (!initialized || source < 0 || !owner_filename)
        return NULL;
    for (unsigned record = 0; record < 3; ++record) {
        if (strcmp(owner_filename, names[source][record]))
            continue;
        if (size)
            *size = record < 2 ? fixture_info[source].bank_size[record] :
                               fixture_info[source].neural_size;
        if (record == 2)
            return source ? radio_checkpoint : audio_checkpoint;
        return source ? radio_banks[record] : audio_banks[record];
    }
    return NULL;
}

bool contexts_models_fixture_metadata(unsigned namespace_id,
                                      contexts_models_fixture_info *out)
{
    int source = source_index(namespace_id);
    if (!initialized || source < 0 || !out)
        return false;
    *out = fixture_info[source];
    return true;
}
