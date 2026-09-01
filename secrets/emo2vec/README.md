# emotion2vec live

Realtime speech-emotion graph. Runs
[emotion2vec+ base](https://huggingface.co/emotion2vec/emotion2vec_plus_base)
in the browser with onnxruntime-web (WebGPU, WASM fallback). No inference
server: the page loads the 373 MB ONNX model, listens to the mic or plays an
audio file, and plots the 9 class probabilities over the last 60 s.

Classes: angry, disgusted, fearful, happy, neutral, other, sad, surprised, unknown.

## Setup

```sh
bun install
mkdir -p models
curl -L -o models/emotion2vec_plus_base.onnx \
  https://huggingface.co/ziyu12345/emotion2vec_plus_base_onnx/resolve/main/emotion2vec_plus_base.onnx
curl -L -o models/emotion2vec_head.json \
  https://huggingface.co/ziyu12345/emotion2vec_plus_base_onnx/resolve/main/emotion2vec_head.json
```

## Run

```sh
bunx serve .
```

Open the printed URL in Chrome. Any static file host works;
`coi-serviceworker.js` adds the COOP/COEP headers that WASM threads need.

## How it works

- `pcm-worklet.js` collects 16 kHz mono samples into 2048-sample chunks.
- `app.js` keeps a ring buffer, runs the model every 250 ms on the last
  1–5 s (window select), mean-pools the frame features, applies the linear
  head from `emotion2vec_head.json`, and plots the softmax.
- Windows below −45 dB RMS are skipped and show as gaps.
- The ONNX export folds the waveform normalization into the graph, so raw
  float32 audio goes straight in.

## Deploy

```sh
bun run build
```

`dist/` is a self-contained static site (~380 MB, mostly the model). Copy it
to any static host. The host must serve `.wasm` as `application/wasm` and
`.mjs` as JavaScript. Hosts with per-file size limits (GitHub Pages,
Cloudflare Pages) reject the 373 MB model.

## Max/MSP external

`max/` is a Max package with `emotion2vec~`, a native MSP object (macOS 14+,
Apple Silicon) that runs emotion2vec+ base as a Core ML model on the GPU
(CPU fallback is automatic). It does not use onnxruntime.

```sh
./max/build.sh                      # fetches the Max SDK, converts the model on first run, builds the external
ln -s "$PWD/max" ~/Documents/Max\ 9/Packages/emotion2vec
```

Restart Max and open `help/emotion2vec~.maxhelp`.

- Inlet: signal at any sample rate (resampled to 16 kHz internally).
- Outlets: probability list (angry disgusted fearful happy neutral other sad
  surprised unknown), top emotion, top probability, info (`db`, `ms`).
- Attributes: `@hop` seconds (default 0.25), `@gate` dBFS (default −45),
  `@model` (absolute path or a name in the Max search path; default
  `models/emotion2vec.mlmodelc` in the package).
- Inference runs on a worker thread; the audio thread only fills a ring buffer.
  One 3 s window takes about 12 ms on an M2 Max GPU; the model loads in under a second.

### Model conversion

`max/convert/convert.py` converts the PyTorch weights
(`emotion2vec/emotion2vec_plus_base`, downloaded on first run) with
coremltools. Waveform normalization, mean pooling, the linear head and the
softmax are inside the model, so it takes raw 16 kHz audio and returns 9
probabilities. Core ML needs a fixed input length; the default is 3 s:

```sh
cd max/convert
uv run convert.py ../models/emotion2vec.mlmodelc --seconds 3
```

A model converted with another `--seconds` changes the analysis window;
point `@model` at it.

`./max/package.sh` assembles the distributable package in `emotion2vec-max/`
(externals, model, help, package-info, README), signs the external with the
Developer ID Application identity in the keychain (hardened runtime,
timestamp) and zips it. With a `max/.env` it also notarizes the zip and
staples the ticket to the external. `max/setup-secrets.sh` writes `.env`
from `.env.template`, resolving the `op://` reference through 1Password.

`max/build/emo_test model.mlmodelc file.wav` classifies a 16-bit mono wav
without Max, for checking the core.
