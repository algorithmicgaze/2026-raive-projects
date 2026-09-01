// Classifies a 16-bit PCM mono wav with the core, resampling to 16 kHz first.
// usage: emo_test model.mlmodelc file.wav
#include "emo_core.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int read_wav(const char *path, float **out, long *n, double *sr) {
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    char id[4];
    unsigned int size;
    fread(id, 1, 4, f); fread(&size, 4, 1, f); fread(id, 1, 4, f); // RIFF size WAVE
    int channels = 1, bits = 16;
    *sr = 0;
    while (fread(id, 1, 4, f) == 4 && fread(&size, 4, 1, f) == 1) {
        if (!memcmp(id, "fmt ", 4)) {
            unsigned char fmt[16];
            fread(fmt, 1, 16, f);
            channels = fmt[2] | fmt[3] << 8;
            *sr = fmt[4] | fmt[5] << 8 | fmt[6] << 16 | fmt[7] << 24;
            bits = fmt[14] | fmt[15] << 8;
            fseek(f, size - 16, SEEK_CUR);
        } else if (!memcmp(id, "data", 4)) {
            if (channels != 1 || bits != 16) { fclose(f); return 0; }
            *n = size / 2;
            short *pcm = malloc(size);
            fread(pcm, 1, size, f);
            *out = malloc(*n * sizeof(float));
            for (long i = 0; i < *n; i++) (*out)[i] = pcm[i] / 32768.0f;
            free(pcm);
            fclose(f);
            return 1;
        } else {
            fseek(f, size + (size & 1), SEEK_CUR);
        }
    }
    fclose(f);
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: %s model.mlmodelc file.wav\n", argv[0]); return 2; }
    float *pcm; long n; double sr;
    if (!read_wav(argv[2], &pcm, &n, &sr)) { fprintf(stderr, "cannot read %s (need 16-bit mono wav)\n", argv[2]); return 1; }

    char err[512];
    emo_core *core = emo_core_new(argv[1], err, sizeof(err));
    if (!core) { fprintf(stderr, "load failed: %s\n", err); return 1; }

    // resample to 16 kHz, then take the first model window (zero-padded if the clip is shorter)
    long n16 = (long)(n * (double)EMO_SR / sr);
    long win = emo_core_window(core);
    float *wave = calloc(n16 > win ? n16 : win, sizeof(float));
    emo_resample(pcm, n, sr, wave, n16);
    printf("wav %.0f Hz, %ld samples -> %ld @16k, model window %ld, %.1f dBFS\n", sr, n, n16, win, emo_rms_db(wave, win));
    float probs[EMO_NCLASS];
    if (emo_core_run(core, wave, probs, err, sizeof(err))) { fprintf(stderr, "run failed: %s\n", err); return 1; }
    for (int k = 0; k < EMO_NCLASS; k++) printf("%-10s %.3f\n", emo_labels[k], probs[k]);
    emo_core_free(core);
    return 0;
}
