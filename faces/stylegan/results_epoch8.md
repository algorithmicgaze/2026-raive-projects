# Variant experiments, epoch 8

Box-side metrics on 48 fixed pairs (onnxruntime CPU). Figment columns come from `stylegan/bench_variants.sh` on the Mac: fp16 model, `onnx-image:inference-total` p50, and PSNR/SSIM of 40 rendered frames against V0's frames.

| variant | flags | G Mparams | GMAC | min/epoch | train l1 / vgg (e8) | L1 e8 | PSNR | SSIM | PSNR vs V0 | SSIM vs V0 | box CPU ms | Figment fp16 ms | fps | frames PSNR vs V0 | frames SSIM vs V0 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V0 |  | 69.0 | 214.2 | 25.1 | 0.0874 / 0.5573 |  |  |  |  |  | 1250 | 181.6 | 5.5 |  |  |
| V1 | --channel-base 16384 | 56.3 | 66.8 | 18.3 |  |  |  |  |  |  |  |  |  |  |  |
| V11 | --channel-base 16384 --skip add --dw-levels 512,256 | 46.5 | 38.1 | 11.6 |  |  |  |  |  |  |  |  |  |  |  |
| V1b | --channel-base 24576 | 61.9 | 128.7 | 22.1 |  |  |  |  |  |  |  |  |  |  |  |
| V2 | --skip add | 56.7 | 149.9 | 15.3 |  |  |  |  |  |  |  |  |  |  |  |
| V3 | --channel-base 16384 --skip add | 46.5 | 46.4 | 16.8 | 0.0801 / 0.5800 |  |  |  |  |  | 238 | 52.5 | 19.0 | 24.60 | 0.7187 |
| V4 | --skip-ch 512:16,256:32,128:64 | 68.3 | 193.3 | 16.8 |  |  |  |  |  |  |  |  |  |  |  |
| V5 | --enc-scale 0.5 --no-enc-top-conv | 42.2 | 146.2 | 15.4 |  |  |  |  |  |  |  |  |  |  |  |
| V6 | --conv1-max-res 128 | 68.7 | 194.9 | 16.4 |  |  |  |  |  |  |  |  |  |  |  |
| V7 | --synth-top 256 --out-refine 16 | 68.7 | 176.8 | 21.8 |  |  |  |  |  |  |  |  |  |  |  |
| V8 | --channel-base 16384 --skip add --enc-scale 0.5 --no-enc-top-conv | 29.4 | 32.6 | 13.1 | 0.0774 / 0.5787 |  |  |  |  |  | 132 | 38.8 | 25.8 | 25.38 | 0.7326 |
| V9 | --channel-base 16384 --skip add --enc-scale 0.5 --no-enc-top-conv --conv1-max-res 128 | 29.3 | 27.8 | 15.4 |  |  |  |  |  |  |  |  |  |  |  |
| pix2pix | pix2pix U-Net, notebook recipe (train_pix2pix_ccm.ipynb), epoch 94 of a 100-epoch run |  |  |  |  | 0.133 | 19.19 | 0.5933 | 20.14 | 0.6301 | 161 | 56.4 | 17.7 | 24.13 | 0.6698 |
