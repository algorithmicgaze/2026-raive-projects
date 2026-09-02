# Diary

Working log for the faces project. Newest entry at the bottom.
Images live in `diary/`, which is git-ignored: they show participants, and
the repo rule (`AGENTS.md`) keeps faces out. The images exist on the machine
that wrote the entry.

## 2026-09-02 19:00 — Kick-off: conditional StyleGAN for the face mesh

- The box (`fdb@100.106.183.123`, RTX 3090 Ti 24 GB, 62 GB RAM, 32 cores,
  torch 2.14 + CUDA 13) runs this project from `secrets/faces/`, a working
  copy outside git. The repo folder is `faces/`; `rsync` keeps the scripts
  and this diary in step until the box folder moves after the run.
- Baseline is `train_pix2pix_ccm.ipynb`: U-Net generator with InstanceNorm,
  PatchGAN, BCE + L1 ×100 + a consistency term on a noised input.
- Dataset `datasets/three_faces`: 14,907 pairs at 1024×512. Left half is the
  photo, right half is a MediaPipe face-mesh wireframe on black. Three
  subjects, many expressions. The mesh fixes the face geometry; hair, clothes
  and background are not in the input at all. That is where the U-Net smears.

Design of `scripts/train_cstylegan.py` (conditional StyleGAN2):

- **Encoder** on the mesh image: one 3×3 conv per level from 512 down to 4,
  strided convs between levels. It gives a feature map per resolution and a
  512-d vector pooled from the 4×4 bottom.
- **Mapping**: `w = MLP([z, embed(cond_vector)])`, 4 layers, lr multiplier
  0.01. The latent is the StyleGAN part; the conditioning vector is the change
  the brief asked for. `w` styles every layer, so pose and expression modulate
  the filters, not only the spatial skips.
- **Synthesis**: the 4×4 encoder feature replaces StyleGAN's constant input.
  Each level: bilinear upsample, concat the encoder feature of that level, two
  modulated 3×3 convs with noise, ToRGB skip sum. Channels follow the StyleGAN2
  rule 32768 / resolution, capped at 512 (64 at 512², 128 at 256², …).
- Modulated conv is written unfused: scale input channels by the style, plain
  `Conv`, scale output channels by the demodulation factor. That exports to
  Conv, Mul, MatMul, Sqrt and runs on onnxruntime-web WebGPU. No InstanceNorm,
  so the fp16 overflow seen on pix2pixHD cannot happen.
- **Discriminator**: StyleGAN2 residual network on `[mesh | photo]` (6
  channels), minibatch-std, non-saturating logistic loss, lazy R1 (γ 10, every
  16 steps). Equalized learning rate everywhere, Adam (0, 0.99), lr 0.002.
- **Generator loss**: adversarial + L1 ×10 + VGG19 perceptual ×10 (ImageNet
  normalized, relu1_1…relu5_1). Lower L1 than the notebook's 100 on purpose:
  the GAN term must own the texture.
- **EMA generator** (half-life 10k images, ramped) makes every sample and
  every export. bf16 autocast for the forward passes, fp32 weights.
- **Export**: EMA generator wrapped with a fixed `z` (seed 0) and the fixed
  per-layer noise buffers, output clamped to [-1, 1]. One input `input`
  `[1, 3, 512, 512]` fp32, one output `output`, static shape, opset 17.
  After every export the script runs the ONNX on onnxruntime CPU and logs the
  max difference against torch and the op list.
- G 69 M params, D 29 M. VRAM peak 18.5 GB at batch 8.

Smoke test (64 pairs, 8 iterations): snapshot, ONNX export and the
onnxruntime check all pass. 414 MB fp32, 683 ms on the box CPU, where
pix2pixHD took 1257 ms and ran 20 fps in Figment. Max torch/ORT difference
0.0035 (TF32 in torch explains it).

## 2026-09-02 19:38 (box time) — Full run started

```
uv run scripts/train_cstylegan.py datasets/three_faces output-cstylegan --epochs 40 --batch-size 8
```

- `output-cstylegan/train.log`, samples `sample_epoch_N.jpg` (rows:
  mesh, EMA output, target for four fixed pairs, one per subject and
  expression), `sample_epoch_N_iter_M.jpg` every 250 iterations.
- Snapshot + ONNX every 2 epochs: `snapshot_epoch_N.pt` (1.5 GB, resumable)
  and `generator_epoch_N.onnx`.
- 1,863 iterations per epoch. Early rate 7.5 img/s and rising, so about
  31 min per epoch and a snapshot roughly every hour. To be confirmed when
  epoch 1 ends.

## 2026-09-02 19:50 (box time) — First look, 4,000 images in

![Epoch 1 iteration 500: mesh, EMA output, target](diary/01_epoch1_iter500.jpg)

Iteration 500 of 1,863. The EMA generator already places a face-shaped blob at
the mesh position with the right skin tone, a dark background and a hint of the
mouth. Everything is still blurred: the EMA half-life ramps up with the image
count, so this is an average of the first minutes. Rate 9.3 img/s at iteration
700, so an epoch is closer to 27 min than 31.

## 2026-09-02 20:05 (box time) — Epoch 1: 25.6 min

![Epoch 1: mesh, EMA output, target](diary/02_epoch1.jpg)

- **25.6 min per epoch** at 9.7 img/s, VRAM peak 18.5 GB. Snapshot + ONNX
  every 2 epochs means one every 51 min. Matches the once-an-hour target;
  the interval stays at 2.
- After one pass over the data the EMA generator draws a head with hair,
  a shirt, a dark background and a mouth that follows the mesh (open mouth in
  row 4). Eyes are not there yet. Identity is confused: rows 1 and 2 (the man)
  come out with a long-haired look. The mesh does not carry identity, so this
  is the multi-subject ambiguity the latent is meant to absorb.
- Losses at the end of epoch 1: d 0.26, adv 4.6, l1 0.23, vgg 0.77. The
  discriminator is ahead (real +3.8, fake −2.1) but R1 keeps it at 0.02,
  so no sign of collapse.

## 2026-09-02 20:32 (box time) — Epoch 2: identities lock in, first ONNX

![Epoch 2: mesh, EMA output, target](diary/03_epoch2.jpg)

- Epoch 2 in 25.0 min. The jump from epoch 1 is large: each row now has the
  right person. Moustache and open collar for the man, long brown hair and
  black top for the woman, teeth in the laughing row. Eyes are open and look
  at the camera. Hair and shirt edges are still soft; hands (row 2, target)
  are absent, as expected: nothing in the mesh says "hands".
- `generator_epoch_2.onnx`: 414 MB, static `[1, 3, 512, 512]`, ops Add,
  Cast, Clip, Concat, Conv, Div, Flatten, Gemm, LeakyRelu, MatMul, Mul,
  ReduceMean, ReduceSum, Resize, Sqrt, Transpose, Unsqueeze. Max difference
  against torch 0.0008. No InstanceNormalization, no Shape plumbing.

![ONNX epoch 2 on pair 12000 via onnxruntime: mesh, output, target](diary/04_onnx_epoch2.jpg)

`scripts/check_onnx.py --pair` on `image-12000.jpg`, onnxruntime CPU,
711 ms. The ONNX path gives the same picture as torch. This pair is a
three-quarter view with a wide smile, and there the model is clearly behind
the frontal rows above: face smeared, hair blocky. Rare poses need more
epochs. Watch this same pair at every export.

## 2026-09-02 21:23 (box time) — Epoch 4: photographic on the frontal rows

![Epoch 4: mesh, EMA output, target](diary/05_epoch4.jpg)

- Four epochs, 1 h 41 min. The frontal rows are close to photographs: skin,
  stubble, collar folds, hair strands, catchlights in the eyes. Row 4 has the
  teeth of the laugh and the mesh's mouth shape. The remaining gap to the
  target is in things the mesh cannot know: the hands in row 2, the exact hair
  parting, the earring.
- Losses: d 1.50 (real −0.27, fake −0.21), adv 1.70, l1 0.112, vgg 0.67,
  r1 0.017. The discriminator went from "ahead" at epoch 1 to balanced: real
  and fake logits are within 0.1 of each other. That is the healthy StyleGAN2
  regime. L1 halved since epoch 1.

![ONNX epoch 4 on pair 12000: mesh, output, target](diary/06_onnx_epoch4.jpg)

`generator_epoch_4.onnx`, 695 ms on CPU, same op list as epoch 2. The
three-quarter view is now a face with the smile and the head turn. The far
eye and the hair volume are still soft: side poses are rare in the data.

Comparison against the pix2pix U-Net is pending: that needs a second run on
the same data with the notebook recipe, after this one, or on another GPU.
