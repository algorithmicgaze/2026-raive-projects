# RAIVE 2026 — creative technology source

Reusable code from the week-long RAIVE summer school: image-to-image training,
ONNX inference in Figment, interactive instruments, audio emotion analysis and
mmWave sensing. These are workshop prototypes; some workflows require a CUDA
GPU, Figment, Max, or sensor hardware.

## Projects

| Folder | Contents | Private participant assets |
| --- | --- | --- |
| `fashion/` | Conditional StyleGAN2 training notebook and Figment patch | Fashion |
| `cars/` | Vehicle extraction, stabilization and interactive highway/piano tools | Cars |
| `faces/` | Face-mesh → image training and Figment patches | Secrets/faces |
| `secrets/emo2vec/` | Browser and Max emotion2vec inference | Secrets/emo2vec |
| `secrets/mmwave-sensor/` | Arduino sensing and MQTT/Max integration | Secrets |
| `secrets/grain-recordings/` | Granular audio Max patches | Secrets |
| `fruit-drama/` | Brain Rot: fruit characters, pose conditioning, training and inference | Brain Rot |
| `figment/` | General detection patch | No bundled assets |

## Code and private assets

This repository contains source, documentation and configuration templates.
The separately shared OneDrive **projects** folder contains media, datasets,
trained models and working logs, grouped into **Fashion**, **Cars**, **Secrets**
and **Brain Rot**, with **Shared interviews** separate.

See [ASSETS.md](ASSETS.md) for model locations and setup. No models, recordings,
notebook outputs, credentials or participant contact details belong here.
First names and third-party license attribution may appear in source.

Python projects use `uv`; standalone scripts declare dependencies inline.
See each project's scripts, notebook or README for commands. Configure your own
GPU host and service accounts; examples contain placeholders only.

## Contributing

Run `python3 tools/check_public_tree.py` before committing. Keep notebook outputs
cleared. Review text, filenames and configuration for personal details: automated
checks cannot recognize every identity. Never add private assets with `git add -f`.
