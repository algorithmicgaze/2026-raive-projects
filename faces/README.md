# Face-mesh image translation

Pix2pix and conditional StyleGAN2 training and ONNX export for Figment.
Start with `train_pix2pix_ccm.ipynb` or `scripts/train_cstylegan.py`.

The private **Secrets/faces/stylegan_new** folder holds the latest supplied
StyleGAN ONNX exports (epoch 10) and resumable PTH checkpoint (epoch 10).
Use the fp16 export for Figment; its input and output remain fp32.
`stylegan_new/three_faces_stylegan_v8_webcam.fgmt` is the current webcam patch.
The `stylegan/` patches and benchmark scripts are historical experiment templates;
their older model weights are not included in the curated share.

Training data and working logs are in **Secrets/faces**. Supply your own data
or restore these private assets locally. Never commit them.
