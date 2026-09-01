// emotion2vec+ base inference core on Core ML. No Max dependencies.
#pragma once
#include <stddef.h>

#define EMO_SR 16000
#define EMO_NCLASS 9

extern const char *emo_labels[EMO_NCLASS];

typedef struct emo_core emo_core;

// Loads a compiled model (.mlmodelc) or a package (.mlpackage, compiled on load).
// Returns NULL and fills err on failure.
emo_core *emo_core_new(const char *model_path, char *err, size_t errlen);
void emo_core_free(emo_core *c);

// Number of 16 kHz samples the model takes per inference (fixed by the model).
long emo_core_window(const emo_core *c);

// Classifies a 16 kHz mono float window of emo_core_window(c) samples.
// Returns 0 on success, fills err otherwise.
int emo_core_run(emo_core *c, const float *wave, float probs[EMO_NCLASS], char *err, size_t errlen);

// Windowed-sinc resample from sr_in to EMO_SR. n_out = n_in * EMO_SR / sr_in.
void emo_resample(const float *in, long n_in, double sr_in, float *out, long n_out);

double emo_rms_db(const float *x, long n);
