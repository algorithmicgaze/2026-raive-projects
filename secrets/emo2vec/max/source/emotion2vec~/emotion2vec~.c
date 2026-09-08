// emotion2vec~ — realtime speech emotion recognition (emotion2vec+ base via onnxruntime).
//
// Inlet:   signal
// Outlets: list of 9 probabilities (angry disgusted fearful happy neutral other sad surprised unknown)
//
// The analysis window length is fixed by the Core ML model (3 s for the bundled one).
//          symbol: top emotion
//          float: top probability
//          info: "db <level>" every hop, "ms <latency>" after each inference

#include "ext.h"
#include "ext_obex.h"
#include "ext_path.h"
#include "ext_systhread.h"
#include "z_dsp.h"
#include "emo_core.h"
#include <dlfcn.h>
#include <libgen.h>
#include <math.h>
#include <string.h>

#define RING_S 6.0

typedef struct _emo {
    t_pxobject ob;

    t_symbol *model;   // path, search-path name, or empty for the package default
    double hop;        // seconds between inferences
    double gate;       // dBFS below which a window is skipped

    // native-rate ring buffer: written by perform, read by the worker
    double sr;
    float *ring;
    long ring_len;
    volatile long ring_pos;
    volatile long ring_total;

    // worker
    t_systhread thread;
    t_systhread_mutex mutex;
    volatile int run;
    volatile int reload;
    emo_core *core;

    // latest result, handed to the main thread through the qelem
    float probs[EMO_NCLASS];
    double latency_ms;
    double level_db;
    int has_probs;
    void *qelem;

    void *out_probs, *out_label, *out_conf, *out_info;
} t_emo;

static t_class *emo_class;

static void *emo_new(t_symbol *s, long argc, t_atom *argv);
static void emo_free(t_emo *x);
static void emo_assist(t_emo *x, void *b, long m, long a, char *s);
static void emo_dsp64(t_emo *x, t_object *dsp64, short *count, double samplerate, long maxvectorsize, long flags);
static void emo_perform64(t_emo *x, t_object *dsp64, double **ins, long numins, double **outs, long numouts,
                          long sampleframes, long flags, void *userparam);
static void *emo_worker(t_emo *x);
static void emo_output(t_emo *x);
static t_max_err emo_model_set(t_emo *x, void *attr, long argc, t_atom *argv);

void ext_main(void *r) {
    t_class *c = class_new("emotion2vec~", (method)emo_new, (method)emo_free, sizeof(t_emo), NULL, A_GIMME, 0);
    class_addmethod(c, (method)emo_dsp64, "dsp64", A_CANT, 0);
    class_addmethod(c, (method)emo_assist, "assist", A_CANT, 0);

    CLASS_ATTR_SYM(c, "model", 0, t_emo, model);
    CLASS_ATTR_ACCESSORS(c, "model", NULL, emo_model_set);
    CLASS_ATTR_LABEL(c, "model", 0, "Model file");
    CLASS_ATTR_DOUBLE(c, "hop", 0, t_emo, hop);
    CLASS_ATTR_FILTER_MIN(c, "hop", 0.05);
    CLASS_ATTR_LABEL(c, "hop", 0, "Hop (s)");
    CLASS_ATTR_DOUBLE(c, "gate", 0, t_emo, gate);
    CLASS_ATTR_LABEL(c, "gate", 0, "Silence gate (dBFS)");

    class_dspinit(c);
    class_register(CLASS_BOX, c);
    emo_class = c;
}

static void *emo_new(t_symbol *s, long argc, t_atom *argv) {
    t_emo *x = (t_emo *)object_alloc(emo_class);
    if (!x) return NULL;

    dsp_setup((t_pxobject *)x, 1);
    x->out_info = outlet_new(x, NULL);
    x->out_conf = floatout(x);
    x->out_label = outlet_new(x, "symbol");
    x->out_probs = listout(x);

    x->model = gensym("");
    x->hop = 0.25;
    x->gate = -45.0;
    x->sr = sys_getsr() > 0 ? sys_getsr() : 44100;
    x->ring_len = (long)(RING_S * x->sr);
    x->ring = (float *)sysmem_newptrclear(x->ring_len * sizeof(float));

    systhread_mutex_new(&x->mutex, 0);
    x->qelem = qelem_new(x, (method)emo_output);

    attr_args_process(x, (short)argc, argv);

    x->run = 1;
    x->reload = 1;
    systhread_create((method)emo_worker, x, 0, 0, 0, &x->thread);
    return x;
}

static void emo_free(t_emo *x) {
    dsp_free((t_pxobject *)x);
    x->run = 0;
    if (x->thread) {
        unsigned int ret;
        systhread_join(x->thread, &ret);
    }
    qelem_free(x->qelem);
    systhread_mutex_free(x->mutex);
    emo_core_free(x->core);
    sysmem_freeptr(x->ring);
}

static void emo_assist(t_emo *x, void *b, long m, long a, char *s) {
    if (m == ASSIST_INLET) {
        strcpy(s, "(signal) audio in");
        return;
    }
    switch (a) {
    case 0: strcpy(s, "(list) probabilities: angry disgusted fearful happy neutral other sad surprised unknown"); break;
    case 1: strcpy(s, "(symbol) top emotion"); break;
    case 2: strcpy(s, "(float) top probability"); break;
    case 3: strcpy(s, "(messages) db <level>, ms <latency>"); break;
    }
}

static t_max_err emo_model_set(t_emo *x, void *attr, long argc, t_atom *argv) {
    x->model = (argc && atom_gettype(argv) == A_SYM) ? atom_getsym(argv) : gensym("");
    x->reload = 1;
    return MAX_ERR_NONE;
}

// ---------- audio ----------

static void emo_dsp64(t_emo *x, t_object *dsp64, short *count, double samplerate, long maxvectorsize, long flags) {
    if (samplerate != x->sr) {
        long len = (long)(RING_S * samplerate);
        float *ring = (float *)sysmem_newptrclear(len * sizeof(float));
        // the worker reads x->ring without a lock; swap under the mutex
        systhread_mutex_lock(x->mutex);
        float *old = x->ring;
        x->ring = ring;
        x->ring_len = len;
        x->ring_pos = 0;
        x->ring_total = 0;
        x->sr = samplerate;
        systhread_mutex_unlock(x->mutex);
        sysmem_freeptr(old);
    }
    object_method(dsp64, gensym("dsp_add64"), x, emo_perform64, 0, NULL);
}

static void emo_perform64(t_emo *x, t_object *dsp64, double **ins, long numins, double **outs, long numouts,
                          long sampleframes, long flags, void *userparam) {
    const double *in = ins[0];
    long pos = x->ring_pos;
    for (long i = 0; i < sampleframes; i++) {
        x->ring[pos] = (float)in[i];
        if (++pos == x->ring_len) pos = 0;
    }
    x->ring_pos = pos;
    x->ring_total += sampleframes;
}

// ---------- model path ----------

// <package>/models/emotion2vec.mlmodelc, relative to this external's bundle.
static int default_model_path(char *out, size_t len) {
    Dl_info info;
    if (!dladdr((void *)emo_new, &info)) return 0;
    char path[MAX_PATH_CHARS];
    strlcpy(path, info.dli_fname, sizeof(path));
    // MacOS/ -> Contents/ -> .mxo/ -> externals/ -> package/
    for (int i = 0; i < 5; i++) strlcpy(path, dirname(path), sizeof(path));
    snprintf(out, len, "%s/models/emotion2vec.mlmodelc", path);
    return 1;
}

static int resolve_model_path(t_emo *x, char *out, size_t len) {
    const char *name = x->model->s_name;
    if (!name[0]) return default_model_path(out, len);
    if (name[0] == '/') {
        strlcpy(out, name, len);
        return 1;
    }
    char filename[MAX_PATH_CHARS];
    short path;
    t_fourcc type;
    strlcpy(filename, name, sizeof(filename));
    if (locatefile_extended(filename, &path, &type, NULL, 0)) return 0;
    return path_toabsolutesystempath(path, filename, out) == MAX_ERR_NONE;
}

// ---------- worker ----------

static void load_model(t_emo *x) {
    char path[MAX_PATH_CHARS], err[512];
    emo_core *old = x->core;
    x->core = NULL;
    emo_core_free(old);

    if (!resolve_model_path(x, path, sizeof(path))) {
        object_error((t_object *)x, "model not found: %s", x->model->s_name);
        return;
    }
    emo_core *core = emo_core_new(path, err, sizeof(err));
    if (!core) {
        object_error((t_object *)x, "cannot load %s: %s", path, err);
        return;
    }
    x->core = core;
    object_post((t_object *)x, "loaded %s (%.1f s window)", path, emo_core_window(core) / (double)EMO_SR);
}

static void *emo_worker(t_emo *x) {
    float *native = NULL, *wave = NULL;
    long native_cap = 0, wave_cap = 0;
    char err[512];

    while (x->run) {
        double t0 = systime_ms();

        if (x->reload) {
            x->reload = 0;
            load_model(x);
        }

        systhread_mutex_lock(x->mutex);
        double sr = x->sr;
        long n_wave = x->core ? emo_core_window(x->core) : 0;
        long n_native = (long)ceil(n_wave * sr / EMO_SR);
        int ready = x->core && x->ring_total >= n_native && n_native <= x->ring_len;
        if (ready) {
            if (n_native > native_cap) {
                native = (float *)sysmem_resizeptr(native, n_native * sizeof(float));
                native_cap = n_native;
            }
            if (n_wave > wave_cap) {
                wave = (float *)sysmem_resizeptr(wave, n_wave * sizeof(float));
                wave_cap = n_wave;
            }
            long pos = x->ring_pos;
            long start = pos - n_native;
            if (start < 0) start += x->ring_len;
            long first = x->ring_len - start;
            if (first > n_native) first = n_native;
            memcpy(native, x->ring + start, first * sizeof(float));
            if (first < n_native) memcpy(native + first, x->ring, (n_native - first) * sizeof(float));
        }
        systhread_mutex_unlock(x->mutex);

        if (ready) {
            emo_resample(native, n_native, sr, wave, n_wave);
            double db = emo_rms_db(wave, n_wave);
            float probs[EMO_NCLASS];
            int has_probs = 0;
            double latency = 0;
            if (db > x->gate) {
                double t1 = systime_ms();
                if (emo_core_run(x->core, wave, probs, err, sizeof(err)) == 0) {
                    has_probs = 1;
                    latency = systime_ms() - t1;
                } else {
                    object_error((t_object *)x, "inference failed: %s", err);
                }
            }
            systhread_mutex_lock(x->mutex);
            x->level_db = db;
            x->has_probs = has_probs;
            if (has_probs) {
                memcpy(x->probs, probs, sizeof(probs));
                x->latency_ms = latency;
            }
            systhread_mutex_unlock(x->mutex);
            qelem_set(x->qelem);
        }

        double wait = x->hop * 1000.0 - (systime_ms() - t0);
        systhread_sleep(wait > 1 ? (long)wait : 1);
    }

    sysmem_freeptr(native);
    sysmem_freeptr(wave);
    systhread_exit(0);
    return NULL;
}

// Main thread: emit the latest result, right to left.
static void emo_output(t_emo *x) {
    float probs[EMO_NCLASS];
    t_atom a[EMO_NCLASS];
    systhread_mutex_lock(x->mutex);
    int has_probs = x->has_probs;
    double db = x->level_db, ms = x->latency_ms;
    memcpy(probs, x->probs, sizeof(probs));
    systhread_mutex_unlock(x->mutex);

    atom_setfloat(a, db);
    outlet_anything(x->out_info, gensym("db"), 1, a);
    if (!has_probs) return;
    atom_setfloat(a, ms);
    outlet_anything(x->out_info, gensym("ms"), 1, a);

    int best = 0;
    for (int k = 1; k < EMO_NCLASS; k++)
        if (probs[k] > probs[best]) best = k;
    outlet_float(x->out_conf, probs[best]);
    outlet_anything(x->out_label, gensym(emo_labels[best]), 0, NULL);
    for (int k = 0; k < EMO_NCLASS; k++) atom_setfloat(a + k, probs[k]);
    outlet_list(x->out_probs, NULL, EMO_NCLASS, a);
}
