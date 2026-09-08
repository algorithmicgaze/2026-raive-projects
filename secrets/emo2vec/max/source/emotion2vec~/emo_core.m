#import <CoreML/CoreML.h>
#import <Foundation/Foundation.h>
#include "emo_core.h"
#include <math.h>
#include <string.h>

const char *emo_labels[EMO_NCLASS] = {"angry", "disgusted", "fearful", "happy", "neutral",
                                      "other", "sad",       "surprised", "unknown"};

struct emo_core {
    MLModel *model;
    long window;
};

static void set_err(char *err, size_t errlen, NSError *e, const char *fallback) {
    snprintf(err, errlen, "%s", e ? e.localizedDescription.UTF8String : fallback);
}

emo_core *emo_core_new(const char *model_path, char *err, size_t errlen) {
    @autoreleasepool {
        NSError *e = nil;
        NSURL *url = [NSURL fileURLWithPath:[NSString stringWithUTF8String:model_path]];
        if ([url.pathExtension isEqualToString:@"mlpackage"]) {
            url = [MLModel compileModelAtURL:url error:&e];
            if (!url) {
                set_err(err, errlen, e, "compile failed");
                return NULL;
            }
        }
        MLModelConfiguration *config = [[MLModelConfiguration alloc] init];
        config.computeUnits = MLComputeUnitsCPUAndGPU;
        MLModel *model = [MLModel modelWithContentsOfURL:url configuration:config error:&e];
        if (!model) {
            set_err(err, errlen, e, "load failed");
            return NULL;
        }
        MLFeatureDescription *in = model.modelDescription.inputDescriptionsByName[@"waveform"];
        NSArray<NSNumber *> *shape = in.multiArrayConstraint.shape;
        if (!in || shape.count != 2 || shape[1].longValue < 1) {
            snprintf(err, errlen, "model has no fixed-length 'waveform' input");
            return NULL;
        }
        emo_core *c = calloc(1, sizeof(*c));
        c->model = (__bridge MLModel *)CFBridgingRetain(model);
        c->window = shape[1].longValue;
        return c;
    }
}

void emo_core_free(emo_core *c) {
    if (!c) return;
    if (c->model) CFBridgingRelease((__bridge CFTypeRef)c->model);
    free(c);
}

long emo_core_window(const emo_core *c) {
    return c->window;
}

int emo_core_run(emo_core *c, const float *wave, float probs[EMO_NCLASS], char *err, size_t errlen) {
    @autoreleasepool {
        NSError *e = nil;
        long n = c->window;
        MLMultiArray *in = [[MLMultiArray alloc] initWithDataPointer:(void *)wave
                                                               shape:@[@1, @(n)]
                                                            dataType:MLMultiArrayDataTypeFloat32
                                                             strides:@[@(n), @1]
                                                         deallocator:nil
                                                               error:&e];
        if (!in) {
            set_err(err, errlen, e, "input array failed");
            return 1;
        }
        MLDictionaryFeatureProvider *features =
            [[MLDictionaryFeatureProvider alloc] initWithDictionary:@{@"waveform" : in} error:&e];
        if (!features) {
            set_err(err, errlen, e, "feature provider failed");
            return 1;
        }
        id<MLFeatureProvider> out = [c->model predictionFromFeatures:features error:&e];
        if (!out) {
            set_err(err, errlen, e, "prediction failed");
            return 1;
        }
        MLMultiArray *p = [out featureValueForName:@"probs"].multiArrayValue;
        if (!p || p.count != EMO_NCLASS) {
            snprintf(err, errlen, "unexpected output (%ld values)", (long)(p ? p.count : 0));
            return 1;
        }
        for (int k = 0; k < EMO_NCLASS; k++) probs[k] = [p[k] floatValue];
        return 0;
    }
}

#define TAPS 32
#define PHASES 256

// Polyphase windowed-sinc low-pass at the output Nyquist, one kernel per fractional phase.
static struct {
    double ratio;
    float coef[PHASES][TAPS];
} kernel;

static void build_kernel(double ratio) {
    const double cutoff = ratio > 1 ? 1.0 / ratio : 1.0;
    for (int p = 0; p < PHASES; p++) {
        double frac = p / (double)PHASES;
        double sum = 0;
        for (int k = 0; k < TAPS; k++) {
            double t = k - TAPS / 2 + 1 - frac;
            double w = 0.5 + 0.5 * cos(M_PI * t / (TAPS / 2));
            double h = (t == 0) ? cutoff : sin(M_PI * cutoff * t) / (M_PI * t);
            kernel.coef[p][k] = (float)(h * w);
            sum += h * w;
        }
        for (int k = 0; k < TAPS; k++) kernel.coef[p][k] /= (float)sum;
    }
    kernel.ratio = ratio;
}

void emo_resample(const float *in, long n_in, double sr_in, float *out, long n_out) {
    if (sr_in == EMO_SR) {
        long n = n_in < n_out ? n_in : n_out;
        memcpy(out, in, n * sizeof(float));
        for (long i = n; i < n_out; i++) out[i] = 0;
        return;
    }
    const double ratio = sr_in / EMO_SR;
    if (kernel.ratio != ratio) build_kernel(ratio);
    for (long i = 0; i < n_out; i++) {
        double center = i * ratio;
        long base = (long)floor(center) - TAPS / 2 + 1;
        int phase = (int)((center - floor(center)) * PHASES) % PHASES;
        const float *c = kernel.coef[phase];
        float acc = 0;
        if (base >= 0 && base + TAPS <= n_in) {
            for (int k = 0; k < TAPS; k++) acc += in[base + k] * c[k];
        } else {
            for (int k = 0; k < TAPS; k++) {
                long j = base + k;
                if (j >= 0 && j < n_in) acc += in[j] * c[k];
            }
        }
        out[i] = acc;
    }
}

double emo_rms_db(const float *x, long n) {
    double sum = 0;
    for (long i = 0; i < n; i++) sum += (double)x[i] * x[i];
    return 10.0 * log10(sum / (double)n + 1e-12);
}
