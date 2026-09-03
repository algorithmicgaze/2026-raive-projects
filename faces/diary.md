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

## 2026-09-02 22:16 (box time) — Epoch 6: the side view catches up

![Epoch 6: mesh, EMA output, target](diary/07_epoch6.jpg)

- Six epochs, 2 h 32 min. Frontal rows change little from epoch 4: sharper
  hair strands, cleaner collar, the earring in row 2 appears. Row 3 keeps
  the closed eyes and downcast look from the mesh.
- Losses: d 1.23 (real +0.75, fake +0.17), adv 1.22, l1 0.110, vgg 0.60.
  L1 has flattened; vgg still falls. The perceptual term is what improves
  now, which fits the visible change: detail, not layout.

![ONNX epoch 6 on pair 12000: mesh, output, target](diary/08_onnx_epoch6.jpg)

The three-quarter view is the clear win of this export: both eyes, the
smile with teeth, hair volume on the far side, the black top. At epoch 4
this pair was a soft face; at epoch 2 a smear. `generator_epoch_6.onnx`,
834 ms on CPU.

## 2026-09-02 23:00 (box time) — Epoch 8, run stopped on purpose

![Epoch 8: mesh, EMA output, target](diary/09_epoch8.jpg)

- Stopped after the epoch-8 export to free the GPU for the speed experiments.
  Snapshots exist for epochs 2, 4, 6 and 8; `snapshot_epoch_8.pt` resumes the
  40-epoch run later (`--epochs 40`, the flag now means "train up to").
- Losses at the end: d 1.25, adv 1.25, l1 0.087, vgg 0.56. Sample rows:
  little visible change since epoch 6, which fits the flat L1. Hair, teeth and
  eyes are the remaining soft spots.

![ONNX epoch 8 on pair 12000: mesh, output, target](diary/10_onnx_epoch8.jpg)

Three-quarter view through `generator_epoch_8.onnx`: the far eye and the
hair volume are now right; the smile is slightly wider than the target.
`generator_epoch_8_fp16.onnx` (147 MB) converts with `stylegan/to_fp16.py`,
max CPU difference 0.0084.

Measured on the Mac (M2 Max, Figment with the PR 109 timing): epoch 4 fp32
198 ms, fp16 158 ms per frame. Too slow for the installation; the target is
20 fps. The plan in `optimize-conditional-stylegan.md` (desk copy) gives the
levers: the generator does 214 GMAC per frame, the channel plan is the big
one, the skip concat and the encoder the second.

## 2026-09-02 23:15 (box time) — Overnight variant queue

`scripts/train_cstylegan.py` grew flags for every variant in the plan, with
defaults that leave V0 byte-identical (the epoch-6 weights load strictly and
reproduce the ONNX to 8e-6): `--channel-base`, `--skip add`, `--skip-ch`,
`--enc-scale`, `--no-enc-top-conv`, `--conv1-max-res`, `--synth-top` +
`--out-refine`, `--dw-levels`. The discriminator keeps its own
`--d-channel-base 32768`, so every variant faces the same critic. The log now
prints the measured GMAC per frame (torch's flop counter on the export graph).

Measured MACs per variant, all matching the plan's predictions:

| variant | flags | GMAC | G params |
| --- | --- | --- | --- |
| V0 | | 214.2 | 69.0 M |
| V1 | `--channel-base 16384` | 66.8 | 56.3 M |
| V1b | `--channel-base 24576` | 128.7 | 61.9 M |
| V2 | `--skip add` | 149.9 | 56.7 M |
| V3 | V1 + V2 | 46.4 | 46.5 M |
| V4 | `--skip-ch 512:16,256:32,128:64` | 193.3 | 68.3 M |
| V5 | `--enc-scale 0.5 --no-enc-top-conv` | 146.2 | 42.2 M |
| V6 | `--conv1-max-res 128` | 194.9 | 68.7 M |
| V7 | `--synth-top 256 --out-refine 16` | 176.8 | 68.7 M |
| V8 | V3 + V5 | 32.6 | 29.4 M |
| V9 | V8 + V6 | 27.8 | 29.3 M |
| V11 | V3 + `--dw-levels 512,256` | 38.1 | 46.5 M |

- `scripts/box/run_experiments.sh`: the queue, in the plan's order (V1, V3,
  V8, V7, V9, V1b, V2, V5, V11, V4, V6), 4 epochs each, snapshot + ONNX at 2
  and 4, fp16 conversion, then `scripts/eval_variant.py` on 48 fixed pairs
  (L1, PSNR, SSIM against the targets and against V0's outputs). V0 is a
  symlink to `output-cstylegan`. Re-run the same command after a power drop:
  every variant resumes from its newest snapshot and finished ones are
  skipped. `output-exp/summary.md` is rewritten after each variant.
- `scripts/export_dw_bench.py` writes the dense-versus-depthwise pair for
  the plan's section 5 micro-benchmark (`output-exp/dwbench/`).
- `stylegan/bench_variants.sh` is the Mac half: pulls the fp16 exports, times
  every one in Figment through `bench.mjs` (`onnx-image:inference-total`),
  renders 40 frames of the test clip per variant, and compares them with V0's
  frames (PSNR, SSIM). `exp/results.md` merges both sides.
- Smoke-tested every variant on the GPU (build, one training step, export,
  onnxruntime match). VRAM: V0-width variants 18.5 GB, V8 10.4 GB, V11 11.8 GB.
- Queue started 23:12. V0 at 25 min per epoch; the small variants should take
  roughly 60 to 80 min for 4 epochs, the wide ones 100. Expect V1, V3, V8,
  V7, V9 and V1b by morning, the rest during the day.

## 2026-09-03 00:05 (box time) — Second box, queue split

- `codespace-4090` (RTX 4090, `codespace@100.91.215.104`) holds the same
  dataset under `secrets/faces/` and was finishing the pix2pix notebook
  (`output/run-01`, resumed run, 24 min per epoch, ONNX up to epoch 94).
  Stopped its kernel at epoch 98 and gave the GPU to the variants.
- `scripts/box/run_experiments.sh` takes variant names as arguments. Split:
  the 3090 Ti keeps V1 (running, 18 min per epoch) then V3, V8, V7, V9, V1b;
  the 4090 runs V2, V5, V11, V4, V6. A hand-over job on the 3090 Ti restarts
  its queue with that list the moment V1 is done. V0's eval outputs were
  copied to the 4090 so its `--ref` numbers use the same reference.
- `stylegan/bench_variants.sh` pulls from both boxes.
- **pix2pix baseline on the box-side metrics** (48 pairs, same protocol):
  the notebook's U-Net at epoch 94 gives L1 0.133, PSNR 19.19, SSIM 0.593.
  V0 at epoch 4: L1 0.110, PSNR 19.84, SSIM 0.633. The conditional StyleGAN
  after 1 h 40 min of training beats the U-Net after a day of it on every
  number, and the eye agrees. The pix2pix ONNX runs in 161 ms on the box CPU
  against 705 ms for V0, so the U-Net stays the speed reference in Figment;
  it goes into the Mac bench as the `pix2pix` row (fp32: its InstanceNorm
  overflows in fp16 on WebGPU).

## 2026-09-03 00:25 (box time) — V1: a third of the MACs, most of the quality

![V1 (channel base 16384) at epoch 4: mesh, EMA output, target](diary/11_v1_epoch4.jpg)

| | GMAC | L1 | PSNR | SSIM | vs V0 PSNR / SSIM | box CPU ms |
| --- | --- | --- | --- | --- | --- | --- |
| V0 epoch 4 | 214 | 0.110 | 19.84 | 0.633 | | 705 |
| V1 epoch 4 | 67 | 0.116 | 19.62 | 0.630 | 24.6 / 0.746 | 295 |

- `--channel-base 16384` trains at 18 min per epoch (V0: 25) and its export
  runs 2.4× faster on the box CPU. The box-side metrics sit within 1 to 3 %
  of V0. On the sample grid the difference does not show at this size; the
  earring in row 2 and the teeth in row 4 are there.
- The plan predicted 57 ms in Figment for V1, close to the 20 fps line. The
  Mac bench decides.
- Hand-over on the 3090 Ti worked: queue now V3, V8, V7, V9, V1b. The 4090
  is on V2 at 16.7 min per epoch.

## 2026-09-03 01:35 (box time) — V3, and the 4090 lost power

![V3 (base 16384, additive skips) at epoch 4: mesh, EMA output, target](diary/12_v3_epoch4.jpg)

| | GMAC | L1 | PSNR | SSIM | vs V0 PSNR / SSIM | box CPU ms |
| --- | --- | --- | --- | --- | --- | --- |
| V0 epoch 4 | 214 | 0.110 | 19.84 | 0.633 | | 705 |
| V1 epoch 4 | 67 | 0.116 | 19.62 | 0.630 | 24.6 / 0.746 | 295 |
| V3 epoch 4 | 46 | 0.115 | 19.81 | 0.625 | 24.3 / 0.733 | 235 |

- V3 (`--channel-base 16384 --skip add`) at 46 GMAC: PSNR equal to V0,
  SSIM 1.3 % lower, and 3× faster than V0 on the box CPU. Row 3 (the
  downcast woman) is the row where V3 is visibly softer than V0: hair and
  the closed eyes. Rows 1, 2 and 4 hold up. 16.8 min per epoch.
- **The 4090 rebooted at 00:32** (uptime says so; the runner log stops
  mid-epoch without an error). V2 was 33 min in, before its first snapshot,
  so it restarts from scratch. This is exactly the case the runner was built
  for: relaunched at 01:30 with the same command, same queue.
- Both boxes now carry an `@reboot` crontab line that starts their share of
  the queue 90 s after boot (`crontab -l` shows it; remove it when the
  experiments are over). Monitors reconnect when a box drops off the tailnet.
- 3090 Ti is on V8 since 01:29, then V7, V9, V1b.

## 2026-09-03 02:40 (box time) — V8 and V2

![V8 (base 16384, additive skips, half encoder) at epoch 4](diary/13_v8_epoch4.jpg)

| | GMAC | L1 | PSNR | SSIM | vs V0 PSNR / SSIM | box CPU ms |
| --- | --- | --- | --- | --- | --- | --- |
| V0 epoch 4 | 214 | 0.110 | 19.84 | 0.633 | | 705 |
| V1 | 67 | 0.116 | 19.62 | 0.630 | 24.6 / 0.746 | 295 |
| V2 (`--skip add`) | 150 | 0.117 | 19.63 | 0.624 | 24.4 / 0.742 | 531 |
| V3 | 46 | 0.115 | 19.81 | 0.625 | 24.3 / 0.733 | 235 |
| V8 | 33 | 0.115 | 19.75 | 0.625 | 24.0 / 0.735 | 181 |

- V8 at a sixth of V0's MACs: the metrics are flat against V3, and the
  export runs 3.9× faster than V0 on the box CPU. On the grid, rows 1 to 3
  match V3; the teeth in row 4 are the first thing to smear. The half-width
  encoder without its 512² conv costs nothing measurable at this epoch: the
  mesh is thin lines, and the plan's guess that the encoder is oversized
  holds.
- V2 (additive skips at full width, trained on the 4090) sits at V1's
  quality with 2.2× V1's MACs, so the skip change alone is not the lever;
  it only pays combined with the narrower channel plan.
- Reading across: all four variants lose 1 to 3 % SSIM against V0 at epoch
  4, and the losses do not grow with the MAC cut. The channel plan is the
  cheap dimension; the Mac timings decide between V3 and V8.
- 3090 Ti on V7 since 02:34, then V9, V1b. 4090 on V5 since 02:31, then
  V11, V4, V6.

## 2026-09-03 04:10 (box time) — V5, V7, and the 4090 rebooted again

![V7 (synthesis to 256, refine at 512) at epoch 4](diary/15_v7_epoch4.jpg)

| | GMAC | L1 | PSNR | SSIM | vs V0 PSNR / SSIM | box CPU ms |
| --- | --- | --- | --- | --- | --- | --- |
| V0 epoch 4 | 214 | 0.110 | 19.84 | 0.633 | | 705 |
| V5 (half encoder) | 146 | 0.121 | 19.45 | 0.615 | 23.5 / 0.726 | 452 |
| V7 (synth to 256 + refine) | 177 | 0.114 | 19.72 | 0.625 | 24.4 / 0.739 | 579 |
| V8 (V3 + V5) | 33 | 0.115 | 19.75 | 0.625 | 24.0 / 0.735 | 181 |

- V5 alone is the worst of the set so far on every metric (PSNR 19.45,
  SSIM 0.615), yet the same encoder diet inside V8 costs nothing against V3.
  A narrow encoder feeding a full-width synthesis is the mismatch; narrow
  into narrow is fine. V5 as a single trim is out.
- V7 keeps quality (SSIM 0.625, same as V3) but saves only 17 % of the MACs
  and runs 22 min per epoch, the slowest of the night. Its 512² level is
  only 16 channels wide, and the grid shows the cost: hair in rows 3 and 4
  is smoother than V3's. Not worth its price; V3 gets the same quality at a
  quarter of V7's MACs.
- **The 4090 rebooted again at 03:33** (second time tonight, both times
  without a shutdown entry, so the power). The `@reboot` crontab line did
  its job: the runner came back 90 s after boot, finished V5's fp16 and eval,
  and started V11, which is already in epoch 3 at 12 min per epoch.
- The monitors' ssh sessions hung through the reboot without noticing.
  Restarted them with keepalives (`ServerAliveInterval 30`), so a drop
  shows up as an event within two minutes.
- 3090 Ti on V9 since 04:03, then V1b. 4090 on V11, then V4, V6.

## 2026-09-03 04:25 (box time) — V11: depthwise is not free

| | GMAC | L1 | PSNR | SSIM | vs V0 PSNR / SSIM | box CPU ms |
| --- | --- | --- | --- | --- | --- | --- |
| V3 | 46 | 0.115 | 19.81 | 0.625 | 24.3 / 0.733 | 235 |
| V11 (V3 + depthwise at 512, 256) | 38 | 0.120 | 19.38 | 0.607 | 23.4 / 0.721 | 201 |

V11 loses 3 % SSIM against V3 for an 18 % MAC cut, and on the box CPU it
is only 15 % faster: the depthwise pass is memory-bound, as the plan
feared. Unless the Figment micro-benchmark (dense versus depthwise pair)
shows a large win on the Apple GPU, V11 is out. 4090 on V4 since 04:23.

## 2026-09-03 05:10 (box time) — V9: best numbers, softest faces

![V9 (V8 + one conv per level at 512 and 256) at epoch 4](diary/16_v9_epoch4.jpg)

| | GMAC | L1 | PSNR | SSIM | vs V0 PSNR / SSIM | box CPU ms |
| --- | --- | --- | --- | --- | --- | --- |
| V0 epoch 4 | 214 | 0.110 | 19.84 | 0.633 | | 705 |
| V8 | 33 | 0.115 | 19.75 | 0.625 | 24.0 / 0.735 | 181 |
| V9 (V8 + `--conv1-max-res 128`) | 28 | 0.113 | 19.80 | 0.630 | 23.7 / 0.736 | 149 |

- V9 is the smallest network of the night (7.7× fewer MACs than V0, 4.7×
  faster on the box CPU) and posts the best box-side numbers of all the
  variants. The grid disagrees: rows 3 and 4 are visibly softer than V8,
  the laugh in row 4 has smudged eyes and flat teeth. The numbers are
  pixel averages on 48 pairs and cannot see it; the differences between
  the small variants (SSIM 0.625 to 0.630) are noise at epoch 4.
- Lesson for the morning: rank by the Figment timing first, then look at the
  frames. The box-side metrics only separate the bad ideas (V5 alone, V11)
  from the rest.
- 3090 Ti on V1b (the last of its share) since 05:05. 4090 on V4 since
  04:23, then V6.

## 2026-09-03 05:35 (box time) — V4

| | GMAC | L1 | PSNR | SSIM | vs V0 PSNR / SSIM | box CPU ms |
| --- | --- | --- | --- | --- | --- | --- |
| V0 epoch 4 | 214 | 0.110 | 19.84 | 0.633 | | 705 |
| V4 (narrow concat skips) | 193 | 0.113 | 19.75 | 0.628 | 25.0 / 0.751 | 545 |

V4 is the closest to V0 in output (PSNR 25.0 against V0's frames, the
highest of the set) but saves only 10 % of the MACs. It confirms that the
skip width is not where the cost sits. 4090 on V6, the last one, since
05:32; 3090 Ti on V1b.
