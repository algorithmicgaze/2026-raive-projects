"""Train a conditional StyleGAN2 generator on paired images and export ONNX.

Pairs: left half = target, right half = input (same layout as the pix2pix
notebook). The conditioning image goes through an encoder that gives (a) a
feature map per resolution, concatenated into the synthesis network, and
(b) a pooled vector that is concatenated with the latent z before the mapping
network. So w = mapping(z, cond) styles every modulated convolution.

Discriminator: StyleGAN2 residual network on [cond | image], non-saturating
logistic loss, lazy R1. Generator: adversarial + L1 + VGG19 perceptual.
Sampling and export use the EMA generator. The ONNX bakes a fixed z and fixed
noise, so the graph has one image input and one image output, static shape,
fp32, opset 17: what Figment's ONNX Image Model node reads.

  uv run scripts/train_cstylegan.py datasets/three_faces output-cstylegan --epochs 40
"""

import argparse
import copy
import glob
import math
import os
import random
import sys
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.transforms.functional as TF
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms
from torchvision.utils import save_image

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ----------------------------------------------------------------------------
# Dataset (same augmentation as the pix2pix notebook)


class PairDataset(Dataset):
    def __init__(self, root_dir, jitter_size=60, augment=True, max_images=None):
        self.root_dir = root_dir
        self.jitter_size = jitter_size
        self.augment = augment
        self.files = sorted(f for f in os.listdir(root_dir) if f.lower().endswith((".jpg", ".png")))
        if max_images:
            self.files = self.files[:max_images]
        self.normalize = transforms.Compose(
            [transforms.ToTensor(), transforms.Normalize((0.5,) * 3, (0.5,) * 3)]
        )

    def __len__(self):
        return len(self.files)

    def pair_size(self):
        w, h = Image.open(os.path.join(self.root_dir, self.files[0])).size
        return w // 2, h

    def __getitem__(self, idx):
        image = Image.open(os.path.join(self.root_dir, self.files[idx]))
        if image.mode != "RGB":
            image = image.convert("RGB")
        w, h = image.size
        target = image.crop((0, 0, w // 2, h))
        cond = image.crop((w // 2, 0, w, h))
        if self.augment:
            w2, h2 = w // 2, h
            size = [h2 + self.jitter_size, w2 + self.jitter_size]
            cond = TF.resize(cond, size, interpolation=TF.InterpolationMode.BICUBIC)
            target = TF.resize(target, size, interpolation=TF.InterpolationMode.BICUBIC)
            i, j, ch, cw = transforms.RandomCrop.get_params(cond, output_size=(h2, w2))
            cond, target = TF.crop(cond, i, j, ch, cw), TF.crop(target, i, j, ch, cw)
            if random.random() > 0.5:
                cond, target = TF.hflip(cond), TF.hflip(target)
        return self.normalize(cond), self.normalize(target)


# ----------------------------------------------------------------------------
# Building blocks with equalized learning rate


def lrelu(x):
    return F.leaky_relu(x, 0.2) * math.sqrt(2)


def normalize_2nd_moment(x, eps=1e-8):
    return x * torch.rsqrt(x.square().mean(dim=1, keepdim=True) + eps)


class EqualLinear(nn.Module):
    def __init__(self, fin, fout, bias=True, bias_init=0.0, lr_mul=1.0, act=False):
        super().__init__()
        self.weight = nn.Parameter(torch.randn(fout, fin) / lr_mul)
        self.bias = nn.Parameter(torch.full([fout], float(bias_init))) if bias else None
        self.scale = lr_mul / math.sqrt(fin)
        self.lr_mul = lr_mul
        self.act = act

    def forward(self, x):
        b = self.bias * self.lr_mul if self.bias is not None else None
        x = F.linear(x, self.weight * self.scale, b)
        return lrelu(x) if self.act else x


class EqualConv(nn.Module):
    def __init__(self, cin, cout, k, bias=True, act=True, stride=1):
        super().__init__()
        self.weight = nn.Parameter(torch.randn(cout, cin, k, k))
        self.bias = nn.Parameter(torch.zeros(cout)) if bias else None
        self.scale = 1 / math.sqrt(cin * k * k)
        self.pad = k // 2
        self.stride = stride
        self.act = act

    def forward(self, x):
        x = F.conv2d(x, self.weight * self.scale, self.bias, stride=self.stride, padding=self.pad)
        return lrelu(x) if self.act else x


class ModConv(nn.Module):
    """StyleGAN2 modulated convolution, unfused form (ONNX friendly)."""

    def __init__(self, cin, cout, k, w_dim, demod=True):
        super().__init__()
        self.weight = nn.Parameter(torch.randn(cout, cin, k, k))
        self.affine = EqualLinear(w_dim, cin, bias_init=1.0)
        self.scale = 1 / math.sqrt(cin * k * k)
        self.pad = k // 2
        self.demod = demod

    def forward(self, x, w):
        s = self.affine(w)  # [B, cin]
        weight = self.weight * self.scale
        x = x * s.to(x.dtype)[:, :, None, None]
        x = F.conv2d(x, weight.to(x.dtype), padding=self.pad)
        if self.demod:
            w2 = weight.float().square().sum(dim=[2, 3])  # [cout, cin]
            d = torch.rsqrt(s.float().square() @ w2.t() + 1e-8)  # [B, cout]
            x = x * d.to(x.dtype)[:, :, None, None]
        return x


class StyledConv(nn.Module):
    def __init__(self, cin, cout, w_dim, size):
        super().__init__()
        self.conv = ModConv(cin, cout, 3, w_dim)
        self.noise_strength = nn.Parameter(torch.zeros([]))
        self.bias = nn.Parameter(torch.zeros(cout))
        self.register_buffer("noise_const", torch.randn(1, 1, size[0], size[1]))

    def forward(self, x, w, noise_mode):
        x = self.conv(x, w)
        if noise_mode == "random":
            noise = torch.randn(x.shape[0], 1, x.shape[2], x.shape[3], device=x.device, dtype=x.dtype)
        elif noise_mode == "const":
            noise = self.noise_const.to(x.dtype)
        else:
            noise = None
        if noise is not None:
            x = x + noise * self.noise_strength.to(x.dtype)
        return lrelu(x + self.bias.to(x.dtype)[None, :, None, None])


class ToRGB(nn.Module):
    def __init__(self, cin, w_dim):
        super().__init__()
        self.conv = ModConv(cin, 3, 1, w_dim, demod=False)
        self.bias = nn.Parameter(torch.zeros(3))

    def forward(self, x, w):
        return self.conv(x, w) + self.bias.to(x.dtype)[None, :, None, None]


def upsample(x):
    return F.interpolate(x, scale_factor=2, mode="bilinear", align_corners=False)


# ----------------------------------------------------------------------------
# Generator


def channel_plan(num_levels, channel_base, channel_max, top_res):
    """Channels per level, level 0 = smallest. StyleGAN2 rule: base / resolution."""
    chans = []
    for i in range(num_levels):
        res = top_res >> (num_levels - 1 - i)
        chans.append(min(channel_base // res, channel_max))
    return chans


class Encoder(nn.Module):
    def __init__(self, chans, sizes, c_dim):
        super().__init__()
        self.from_rgb = EqualConv(3, chans[-1], 1)
        self.convs = nn.ModuleList()
        self.downs = nn.ModuleList()
        for i in range(len(chans) - 1, 0, -1):
            self.convs.append(EqualConv(chans[i], chans[i], 3))
            self.downs.append(EqualConv(chans[i], chans[i - 1], 3, stride=2))
        self.conv0 = EqualConv(chans[0], chans[0], 3)
        h0, w0 = sizes[0]
        self.fc = EqualLinear(chans[0] * h0 * w0, c_dim, act=True)

    def forward(self, cond):
        x = self.from_rgb(cond)
        feats = []
        for conv, down in zip(self.convs, self.downs):
            x = conv(x)
            feats.append(x)
            x = down(x)
        x = self.conv0(x)
        feats.append(x)
        feats.reverse()  # level 0 first
        c = self.fc(x.flatten(1))
        return feats, c


class Mapping(nn.Module):
    def __init__(self, z_dim, c_dim, w_dim, num_layers=4, lr_mul=0.01):
        super().__init__()
        self.embed = EqualLinear(c_dim, w_dim)
        layers = []
        fin = z_dim + w_dim
        for _ in range(num_layers):
            layers.append(EqualLinear(fin, w_dim, lr_mul=lr_mul, act=True))
            fin = w_dim
        self.layers = nn.ModuleList(layers)
        self.register_buffer("w_avg", torch.zeros(w_dim))

    def forward(self, z, c, psi=1.0):
        x = torch.cat([normalize_2nd_moment(z), normalize_2nd_moment(self.embed(c))], dim=1)
        for layer in self.layers:
            x = layer(x)
        if self.training:
            with torch.no_grad():
                self.w_avg.copy_(x.detach().float().mean(0).lerp(self.w_avg, 0.995))
        if psi != 1.0:
            x = self.w_avg.lerp(x, psi)
        return x


class Synthesis(nn.Module):
    def __init__(self, chans, sizes, w_dim):
        super().__init__()
        self.conv_in = StyledConv(chans[0], chans[0], w_dim, sizes[0])
        self.rgb_in = ToRGB(chans[0], w_dim)
        self.conv0 = nn.ModuleList()
        self.conv1 = nn.ModuleList()
        self.to_rgb = nn.ModuleList()
        for i in range(1, len(chans)):
            self.conv0.append(StyledConv(chans[i - 1] + chans[i], chans[i], w_dim, sizes[i]))
            self.conv1.append(StyledConv(chans[i], chans[i], w_dim, sizes[i]))
            self.to_rgb.append(ToRGB(chans[i], w_dim))

    def forward(self, feats, w, noise_mode):
        x = self.conv_in(feats[0], w, noise_mode)
        rgb = self.rgb_in(x, w)
        for i, (conv0, conv1, to_rgb) in enumerate(zip(self.conv0, self.conv1, self.to_rgb)):
            x = torch.cat([upsample(x), feats[i + 1]], dim=1)
            x = conv0(x, w, noise_mode)
            x = conv1(x, w, noise_mode)
            rgb = upsample(rgb) + to_rgb(x, w)
        return rgb


class Generator(nn.Module):
    def __init__(self, width, height, z_dim=512, w_dim=512, c_dim=512,
                 channel_base=32768, channel_max=512, num_levels=8, mapping_layers=4):
        super().__init__()
        assert width % (1 << (num_levels - 1)) == 0 and height % (1 << (num_levels - 1)) == 0
        self.z_dim = z_dim
        sizes = [(height >> (num_levels - 1 - i), width >> (num_levels - 1 - i)) for i in range(num_levels)]
        chans = channel_plan(num_levels, channel_base, channel_max, max(width, height))
        self.encoder = Encoder(chans, sizes, c_dim)
        self.mapping = Mapping(z_dim, c_dim, w_dim, mapping_layers)
        self.synthesis = Synthesis(chans, sizes, w_dim)
        self.chans = chans

    def forward(self, cond, z, noise_mode="random", psi=1.0):
        feats, c = self.encoder(cond)
        if z.shape[0] != c.shape[0]:
            z = z.repeat(c.shape[0], 1)
        w = self.mapping(z, c, psi)
        return self.synthesis(feats, w, noise_mode)


class ExportGenerator(nn.Module):
    """Fixed z, fixed noise, clamped output: one image in, one image out."""

    def __init__(self, generator, z, psi=1.0):
        super().__init__()
        self.generator = generator
        self.register_buffer("z", z)
        self.psi = psi

    def forward(self, cond):
        return self.generator(cond, self.z, noise_mode="const", psi=self.psi).clamp(-1, 1)


# ----------------------------------------------------------------------------
# Discriminator


class MinibatchStd(nn.Module):
    def __init__(self, group=4):
        super().__init__()
        self.group = group

    def forward(self, x):
        n, c, h, w = x.shape
        g = min(self.group, n)
        while n % g != 0:
            g -= 1
        y = x.float().reshape(g, -1, c, h, w)
        y = y - y.mean(dim=0)
        y = y.square().mean(dim=0)
        y = (y + 1e-8).sqrt().mean(dim=[1, 2, 3])  # [n/g]
        y = y.reshape(-1, 1, 1, 1).repeat(g, 1, h, w)
        return torch.cat([x, y.to(x.dtype)], dim=1)


class DBlock(nn.Module):
    def __init__(self, cin, cout):
        super().__init__()
        self.conv0 = EqualConv(cin, cin, 3)
        self.conv1 = EqualConv(cin, cout, 3, stride=2)
        self.skip = EqualConv(cin, cout, 1, bias=False, act=False)

    def forward(self, x):
        y = self.skip(F.avg_pool2d(x, 2))
        x = self.conv1(self.conv0(x))
        return (x + y) / math.sqrt(2)


class Discriminator(nn.Module):
    def __init__(self, width, height, channel_base=32768, channel_max=512, num_levels=8):
        super().__init__()
        chans = channel_plan(num_levels, channel_base, channel_max, max(width, height))
        self.from_rgb = EqualConv(6, chans[-1], 1)
        self.blocks = nn.ModuleList(DBlock(chans[i], chans[i - 1]) for i in range(num_levels - 1, 0, -1))
        self.mbstd = MinibatchStd()
        self.conv = EqualConv(chans[0] + 1, chans[0], 3)
        h0, w0 = height >> (num_levels - 1), width >> (num_levels - 1)
        self.fc = EqualLinear(chans[0] * h0 * w0, chans[0], act=True)
        self.out = EqualLinear(chans[0], 1)

    def forward(self, cond, image):
        x = self.from_rgb(torch.cat([cond, image], dim=1))
        for block in self.blocks:
            x = block(x)
        x = self.conv(self.mbstd(x))
        return self.out(self.fc(x.flatten(1)))


# ----------------------------------------------------------------------------
# Perceptual loss


class VGGLoss(nn.Module):
    def __init__(self):
        super().__init__()
        vgg = models.vgg19(weights=models.VGG19_Weights.IMAGENET1K_V1).features.eval()
        for p in vgg.parameters():
            p.requires_grad_(False)
        bounds = [0, 2, 7, 12, 21, 30]  # relu1_1, relu2_1, relu3_1, relu4_1, relu5_1
        self.slices = nn.ModuleList(nn.Sequential(*vgg[bounds[i]:bounds[i + 1]]) for i in range(5))
        self.weights = [1 / 32, 1 / 16, 1 / 8, 1 / 4, 1.0]
        self.register_buffer("mean", torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1))

    def forward(self, x, y):
        x = ((x + 1) / 2 - self.mean) / self.std
        y = ((y + 1) / 2 - self.mean) / self.std
        loss = 0.0
        for w, s in zip(self.weights, self.slices):
            x, y = s(x), s(y)
            loss = loss + w * F.l1_loss(x, y.detach())
        return loss


# ----------------------------------------------------------------------------
# Export and checks


def export_onnx(g_ema, path, width, height, z, psi):
    model = ExportGenerator(copy.deepcopy(g_ema).float().eval(), z, psi).to(device).eval()
    dummy = torch.randn(1, 3, height, width, device=device)
    with torch.no_grad():
        ref = model(dummy)
    torch.onnx.export(
        model, dummy, path,
        export_params=True, opset_version=17, do_constant_folding=True,
        input_names=["input"], output_names=["output"],
        dynamo=False,
    )
    return dummy, ref


def check_onnx(path, dummy, ref):
    import onnx
    import onnxruntime as ort

    model = onnx.load(path)
    ops = sorted({n.op_type for n in model.graph.node})
    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0]
    t0 = time.time()
    out = sess.run(None, {inp.name: dummy.cpu().numpy()})[0]
    dt = time.time() - t0
    diff = float(np.abs(out - ref.cpu().numpy()).max())
    size = os.path.getsize(path) / 1e6
    return f"onnx {os.path.basename(path)}: {size:.0f} MB, input {inp.shape}, cpu {dt * 1000:.0f} ms, max|torch-ort| {diff:.4f}, ops {ops}"


# ----------------------------------------------------------------------------
# Training


def latest(pattern):
    files = glob.glob(pattern)
    return max(files, key=os.path.getctime) if files else None


def requires_grad(module, flag):
    for p in module.parameters():
        p.requires_grad_(flag)


@torch.no_grad()
def ema_update(g_ema, g, beta):
    for p_ema, p in zip(g_ema.parameters(), g.parameters()):
        p_ema.lerp_(p, 1 - beta)
    for b_ema, b in zip(g_ema.buffers(), g.buffers()):
        b_ema.copy_(b)


@torch.no_grad()
def save_sample(g_ema, fixed_cond, fixed_target, z, path):
    g_ema.eval()
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
        fake = g_ema(fixed_cond, z, noise_mode="const").float().clamp(-1, 1)
    rows = torch.cat([fixed_cond, fake, fixed_target], dim=3)  # [cond | fake | target] per row
    save_image((rows + 1) / 2, path, nrow=1, padding=0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_dir")
    ap.add_argument("output_dir")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--lr", type=float, default=0.002)
    ap.add_argument("--lambda-l1", type=float, default=10.0)
    ap.add_argument("--lambda-vgg", type=float, default=10.0)
    ap.add_argument("--r1-gamma", type=float, default=10.0)
    ap.add_argument("--r1-interval", type=int, default=16)
    ap.add_argument("--ema-kimg", type=float, default=10.0)
    ap.add_argument("--channel-base", type=int, default=32768)
    ap.add_argument("--channel-max", type=int, default=512)
    ap.add_argument("--psi", type=float, default=1.0, help="truncation for export (1 = none)")
    ap.add_argument("--sample-interval", type=int, default=250)
    ap.add_argument("--snapshot-interval", type=int, default=2, help="epochs between snapshots")
    ap.add_argument("--restart", action="store_true", help="ignore existing snapshots")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-images", type=int, default=None, help="use a subset (smoke test)")
    ap.add_argument("--max-iters", type=int, default=None, help="stop after N iterations (smoke test)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    random.seed(args.seed)
    torch.backends.cudnn.benchmark = True
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    os.makedirs(args.output_dir, exist_ok=True)
    log_path = os.path.join(args.output_dir, "training_log.txt")

    def log(msg):
        print(msg, flush=True)
        with open(log_path, "a") as f:
            f.write(msg + "\n")

    dataset = PairDataset(args.input_dir, max_images=args.max_images)
    width, height = dataset.pair_size()
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, num_workers=args.workers,
                        pin_memory=True, drop_last=True, persistent_workers=args.workers > 0)
    fixed = PairDataset(args.input_dir, augment=False)
    idx = [int(i) for i in np.linspace(0, len(fixed) - 1, 4)]
    fixed_cond = torch.stack([fixed[i][0] for i in idx]).to(device)
    fixed_target = torch.stack([fixed[i][1] for i in idx]).to(device)

    G = Generator(width, height, channel_base=args.channel_base, channel_max=args.channel_max).to(device)
    D = Discriminator(width, height, channel_base=args.channel_base, channel_max=args.channel_max).to(device)
    G_ema = copy.deepcopy(G).eval()
    requires_grad(G_ema, False)
    vgg = VGGLoss().to(device) if args.lambda_vgg > 0 else None
    opt_G = torch.optim.Adam(G.parameters(), lr=args.lr, betas=(0.0, 0.99), eps=1e-8)
    opt_D = torch.optim.Adam(D.parameters(), lr=args.lr, betas=(0.0, 0.99), eps=1e-8)
    export_z = torch.randn(1, G.z_dim, generator=torch.Generator().manual_seed(args.seed)).to(device)

    n_g = sum(p.numel() for p in G.parameters()) / 1e6
    n_d = sum(p.numel() for p in D.parameters()) / 1e6
    log(f"dataset {len(dataset)} pairs, {width}x{height}, batch {args.batch_size}, "
        f"G {n_g:.1f}M params (channels {G.chans}), D {n_d:.1f}M params")

    start_epoch, step = 1, 0
    snapshot = None if args.restart else latest(os.path.join(args.output_dir, "snapshot_epoch_*.pt"))
    if snapshot:
        ckpt = torch.load(snapshot, map_location=device, weights_only=False)
        G.load_state_dict(ckpt["G"])
        D.load_state_dict(ckpt["D"])
        G_ema.load_state_dict(ckpt["G_ema"])
        opt_G.load_state_dict(ckpt["opt_G"])
        opt_D.load_state_dict(ckpt["opt_D"])
        start_epoch, step = ckpt["epoch"] + 1, ckpt["step"]
        log(f"resumed from {snapshot} (epoch {ckpt['epoch']}, step {step})")

    autocast = lambda: torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda")  # noqa: E731
    stats = {}
    t_epoch = time.time()

    def snapshot_and_export(epoch):
        path = os.path.join(args.output_dir, f"snapshot_epoch_{epoch}.pt")
        torch.save({"G": G.state_dict(), "D": D.state_dict(), "G_ema": G_ema.state_dict(),
                    "opt_G": opt_G.state_dict(), "opt_D": opt_D.state_dict(),
                    "epoch": epoch, "step": step, "args": vars(args)}, path)
        onnx_path = os.path.join(args.output_dir, f"generator_epoch_{epoch}.onnx")
        try:
            dummy, ref = export_onnx(G_ema, onnx_path, width, height, export_z, args.psi)
            log(check_onnx(onnx_path, dummy, ref))
        except Exception as e:  # never let an export problem kill the run
            log(f"ONNX export failed: {e!r}")

    for epoch in range(start_epoch, start_epoch + args.epochs):
        G.train()
        D.train()
        for it, (cond, real) in enumerate(loader, 1):
            cond, real = cond.to(device, non_blocking=True), real.to(device, non_blocking=True)
            b = cond.shape[0]

            # --- Discriminator ---
            requires_grad(D, True)
            requires_grad(G, False)
            z = torch.randn(b, G.z_dim, device=device)
            with autocast():
                with torch.no_grad():
                    fake = G(cond, z)
                d_fake = D(cond, fake)
                d_real = D(cond, real)
                loss_D = F.softplus(d_fake).mean() + F.softplus(-d_real).mean()
            opt_D.zero_grad(set_to_none=True)
            loss_D.backward()
            stats["d"] = loss_D.item()
            stats["d_real"] = d_real.float().mean().item()
            stats["d_fake"] = d_fake.float().mean().item()

            if args.r1_gamma > 0 and step % args.r1_interval == 0:
                real_r1 = real.detach().requires_grad_(True)
                with autocast():
                    d_real = D(cond, real_r1)
                grad, = torch.autograd.grad(d_real.float().sum(), real_r1, create_graph=True)
                r1 = grad.float().square().sum(dim=[1, 2, 3]).mean()
                (r1 * (args.r1_gamma / 2) * args.r1_interval).backward()
                stats["r1"] = r1.item()
            opt_D.step()

            # --- Generator ---
            requires_grad(D, False)
            requires_grad(G, True)
            z = torch.randn(b, G.z_dim, device=device)
            with autocast():
                fake = G(cond, z)
                g_adv = F.softplus(-D(cond, fake)).mean()
                g_l1 = F.l1_loss(fake.float(), real)
                g_vgg = vgg(fake.float(), real) if vgg is not None else torch.zeros((), device=device)
                loss_G = g_adv + args.lambda_l1 * g_l1 + args.lambda_vgg * g_vgg
            opt_G.zero_grad(set_to_none=True)
            loss_G.backward()
            opt_G.step()
            stats.update(g=loss_G.item(), g_adv=g_adv.item(), l1=g_l1.item(), vgg=g_vgg.item())

            # --- EMA ---
            step += 1
            cur_nimg = step * args.batch_size
            ema_nimg = min(args.ema_kimg * 1000, cur_nimg * 0.05)
            beta = 0.5 ** (args.batch_size / max(ema_nimg, 1e-8))
            ema_update(G_ema, G, beta)

            if step % 50 == 0:
                rate = it * args.batch_size / (time.time() - t_epoch)
                log(f"epoch {epoch} iter {it}/{len(loader)} | d {stats['d']:.3f} "
                    f"(real {stats['d_real']:+.2f} fake {stats['d_fake']:+.2f}) r1 {stats.get('r1', 0):.3f} | "
                    f"g {stats['g']:.3f} adv {stats['g_adv']:.3f} l1 {stats['l1']:.4f} vgg {stats['vgg']:.4f} | "
                    f"{rate:.1f} img/s, ema beta {beta:.5f}")
            if step % args.sample_interval == 0:
                save_sample(G_ema, fixed_cond, fixed_target, export_z,
                            os.path.join(args.output_dir, f"sample_epoch_{epoch}_iter_{it}.jpg"))
            if args.max_iters and step >= args.max_iters:
                break

        log(f"epoch {epoch} done in {(time.time() - t_epoch) / 60:.1f} min, "
            f"vram peak {torch.cuda.max_memory_allocated() / 1e9:.1f} GB" if device.type == "cuda" else f"epoch {epoch} done")
        t_epoch = time.time()
        save_sample(G_ema, fixed_cond, fixed_target, export_z, os.path.join(args.output_dir, f"sample_epoch_{epoch}.jpg"))
        if epoch % args.snapshot_interval == 0 or (args.max_iters and step >= args.max_iters):
            snapshot_and_export(epoch)
        if args.max_iters and step >= args.max_iters:
            break


if __name__ == "__main__":
    main()
