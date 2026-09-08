"""Train a pix2pixHD global generator on a folder of paired images and export ONNX.

Pairs: left half = target, right half = input (same as train_pix2pix.py).
Model: ResNet global generator (4 down-samplings, 9 residual blocks, instance
norm, reflection padding), two-scale PatchGAN discriminator, LSGAN loss,
discriminator feature matching, VGG19 perceptual loss. Same recipe as
figmentapp/pix2pix `train_pix2pixhd.ipynb`. The ONNX loads in Figment's
ONNX Image Model node. Sides must divide by 16.

  uv run scripts/train_pix2pixhd.py DATASET_DIR OUTPUT_DIR --epochs 60 --batch-size 4
"""

import argparse
import glob
import math
import os
import sys
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import models, transforms
from torchvision.utils import save_image
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_pix2pix import Pix2PixDataset  # noqa: E402

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def norm_layer(channels):
    return nn.InstanceNorm2d(channels, affine=False, track_running_stats=False)


def weights_init(module):
    name = module.__class__.__name__
    if "Conv" in name:
        nn.init.normal_(module.weight.data, 0.0, 0.02)
        if getattr(module, "bias", None) is not None:
            nn.init.zeros_(module.bias.data)


class ResnetBlock(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.conv_block = nn.Sequential(
            nn.ReflectionPad2d(1), nn.Conv2d(dim, dim, 3), norm_layer(dim), nn.ReLU(True),
            nn.ReflectionPad2d(1), nn.Conv2d(dim, dim, 3), norm_layer(dim),
        )

    def forward(self, x):
        return x + self.conv_block(x)


class GlobalGenerator(nn.Module):
    def __init__(self, input_nc=3, output_nc=3, ngf=64, n_downsampling=4, n_blocks=9):
        super().__init__()
        model = [nn.ReflectionPad2d(3), nn.Conv2d(input_nc, ngf, 7), norm_layer(ngf), nn.ReLU(True)]
        for i in range(n_downsampling):
            mult = 2 ** i
            model += [nn.Conv2d(ngf * mult, ngf * mult * 2, 3, stride=2, padding=1), norm_layer(ngf * mult * 2), nn.ReLU(True)]
        mult = 2 ** n_downsampling
        model += [ResnetBlock(ngf * mult) for _ in range(n_blocks)]
        for i in range(n_downsampling):
            mult = 2 ** (n_downsampling - i)
            model += [nn.ConvTranspose2d(ngf * mult, ngf * mult // 2, 3, stride=2, padding=1, output_padding=1),
                      norm_layer(ngf * mult // 2), nn.ReLU(True)]
        model += [nn.ReflectionPad2d(3), nn.Conv2d(ngf, output_nc, 7), nn.Tanh()]
        self.model = nn.Sequential(*model)

    def forward(self, x):
        return self.model(x)


class NLayerDiscriminator(nn.Module):
    """PatchGAN that returns every intermediate feature map (for feature matching)."""

    def __init__(self, input_nc, ndf=64, n_layers=3):
        super().__init__()
        kw, padw = 4, int(math.ceil((4 - 1.0) / 2))
        blocks = [nn.Sequential(nn.Conv2d(input_nc, ndf, kw, stride=2, padding=padw), nn.LeakyReLU(0.2, True))]
        nf = ndf
        for _ in range(1, n_layers):
            nf_prev, nf = nf, min(nf * 2, 512)
            blocks.append(nn.Sequential(nn.Conv2d(nf_prev, nf, kw, stride=2, padding=padw), norm_layer(nf), nn.LeakyReLU(0.2, True)))
        nf_prev, nf = nf, min(nf * 2, 512)
        blocks.append(nn.Sequential(nn.Conv2d(nf_prev, nf, kw, stride=1, padding=padw), norm_layer(nf), nn.LeakyReLU(0.2, True)))
        blocks.append(nn.Conv2d(nf, 1, kw, stride=1, padding=padw))
        self.blocks = nn.ModuleList(blocks)

    def forward(self, x):
        features = []
        for block in self.blocks:
            x = block(x)
            features.append(x)
        return features


class MultiscaleDiscriminator(nn.Module):
    def __init__(self, input_nc, ndf=64, n_layers=3, num_D=2):
        super().__init__()
        self.discriminators = nn.ModuleList([NLayerDiscriminator(input_nc, ndf, n_layers) for _ in range(num_D)])
        self.downsample = nn.AvgPool2d(3, stride=2, padding=1, count_include_pad=False)

    def forward(self, x):
        result = []
        for i, d in enumerate(self.discriminators):
            result.append(d(x))
            if i != len(self.discriminators) - 1:
                x = self.downsample(x)
        return result


class GANLoss(nn.Module):
    """LSGAN on the last output of every scale."""

    def __init__(self):
        super().__init__()
        self.loss = nn.MSELoss()

    def forward(self, predictions, target_is_real):
        total = 0.0
        for scale in predictions:
            pred = scale[-1]
            total = total + self.loss(pred, torch.full_like(pred, 1.0 if target_is_real else 0.0))
        return total


def feature_matching_loss(pred_fake, pred_real, lambda_feat):
    criterion = nn.L1Loss()
    feat_weights = 4.0 / len(pred_fake[0])
    d_weights = 1.0 / len(pred_fake)
    loss = 0.0
    for scale_fake, scale_real in zip(pred_fake, pred_real):
        for f_fake, f_real in zip(scale_fake[:-1], scale_real[:-1]):
            loss = loss + d_weights * feat_weights * criterion(f_fake, f_real.detach()) * lambda_feat
    return loss


class VGGLoss(nn.Module):
    def __init__(self):
        super().__init__()
        features = models.vgg19(weights=models.VGG19_Weights.IMAGENET1K_V1).features
        bounds = [0, 2, 7, 12, 21, 30]
        self.slices = nn.ModuleList([nn.Sequential(*[features[i] for i in range(a, b)]) for a, b in zip(bounds, bounds[1:])])
        for p in self.parameters():
            p.requires_grad = False
        self.criterion = nn.L1Loss()
        self.weights = [1.0 / 32, 1.0 / 16, 1.0 / 8, 1.0 / 4, 1.0]

    def forward(self, x, y):
        loss = 0.0
        for w, s in zip(self.weights, self.slices):
            x, y = s(x), s(y)
            loss = loss + w * self.criterion(x, y.detach())
        return loss


def export_onnx(generator, path, width, height):
    generator.eval()
    dummy = torch.randn(1, 3, height, width, device=device)
    with torch.no_grad():
        generator(dummy)
    torch.onnx.export(
        generator, dummy, path,
        export_params=True, opset_version=17, do_constant_folding=True,
        input_names=["input"], output_names=["output"],
        dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
        dynamo=False,
    )
    generator.train()


def latest(pattern):
    files = glob.glob(pattern)
    return max(files, key=os.path.getctime) if files else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_dir")
    ap.add_argument("output_dir")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--lambda-feat", type=float, default=10.0)
    ap.add_argument("--no-vgg", action="store_true", help="train without the VGG perceptual loss")
    ap.add_argument("--n-blocks", type=int, default=9)
    ap.add_argument("--sample-interval", type=int, default=100)
    ap.add_argument("--snapshot-interval", type=int, default=5)
    ap.add_argument("--restart", action="store_true", help="ignore existing snapshots")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    log_path = os.path.join(args.output_dir, "training_log.txt")
    transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.5,) * 3, (0.5,) * 3)])
    dataset = Pix2PixDataset(args.input_dir, transform=transform)
    dataloader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, num_workers=args.workers,
                            drop_last=True, pin_memory=True)
    sample = dataset[0][0]
    height, width = sample.shape[1], sample.shape[2]
    if height % 16 or width % 16:
        sys.exit(f"pair halves are {width}x{height}; both sides must divide by 16")
    print(f"{len(dataset)} pairs, input {width}x{height}")

    generator = GlobalGenerator(n_blocks=args.n_blocks).to(device)
    discriminator = MultiscaleDiscriminator(input_nc=6).to(device)
    generator.apply(weights_init)
    discriminator.apply(weights_init)
    criterion_gan = GANLoss().to(device)
    criterion_vgg = None if args.no_vgg else VGGLoss().to(device)
    g_optimizer = optim.Adam(generator.parameters(), lr=args.lr, betas=(0.5, 0.999))
    d_optimizer = optim.Adam(discriminator.parameters(), lr=args.lr, betas=(0.5, 0.999))

    fixed_input, fixed_target = (t[:4] for t in next(iter(dataloader)))

    start_epoch = 1
    snapshot = None if args.restart else latest(os.path.join(args.output_dir, "snapshot_epoch_*.pth"))
    if snapshot:
        ck = torch.load(snapshot, map_location=device, weights_only=False)
        generator.load_state_dict(ck["generator"])
        discriminator.load_state_dict(ck["discriminator"])
        g_optimizer.load_state_dict(ck["g_optimizer"])
        d_optimizer.load_state_dict(ck["d_optimizer"])
        start_epoch = ck["epoch"] + 1
        print(f"Resuming from epoch {ck['epoch']}")

    for epoch in range(start_epoch, start_epoch + args.epochs):
        for i, (input_img, target_img) in enumerate(tqdm(dataloader, file=sys.stdout, desc=f"epoch {epoch}")):
            input_img = input_img.to(device, non_blocking=True)
            target_img = target_img.to(device, non_blocking=True)

            d_optimizer.zero_grad(set_to_none=True)
            with torch.no_grad():
                fake_detached = generator(input_img)
            pred_real = discriminator(torch.cat([input_img, target_img], 1))
            pred_fake = discriminator(torch.cat([input_img, fake_detached], 1))
            loss_d = 0.5 * (criterion_gan(pred_real, True) + criterion_gan(pred_fake, False))
            loss_d.backward()
            d_optimizer.step()

            g_optimizer.zero_grad(set_to_none=True)
            fake_img = generator(input_img)
            pred_fake = discriminator(torch.cat([input_img, fake_img], 1))
            with torch.no_grad():
                pred_real = discriminator(torch.cat([input_img, target_img], 1))
            loss_g_gan = criterion_gan(pred_fake, True)
            loss_g_feat = feature_matching_loss(pred_fake, pred_real, args.lambda_feat)
            loss_g_vgg = criterion_vgg(fake_img, target_img) * args.lambda_feat if criterion_vgg else torch.zeros((), device=device)
            loss_g = loss_g_gan + loss_g_feat + loss_g_vgg
            loss_g.backward()
            g_optimizer.step()

            if i % 10 == 0:
                msg = (f"Epoch {epoch} iter {i} | d: {loss_d.item():.4f} | g_gan: {loss_g_gan.item():.4f} | "
                       f"g_feat: {loss_g_feat.item():.4f} | g_vgg: {loss_g_vgg.item():.4f}")
                with open(log_path, "a") as f:
                    f.write(msg + "\n")

            if i % args.sample_interval == 0:
                generator.eval()
                with torch.no_grad():
                    fake = generator(fixed_input.to(device)).cpu()
                grid = torch.cat((fixed_input, fake, fixed_target), -1)
                save_image((grid + 1) / 2, f"{args.output_dir}/epoch_{epoch:03d}_iter_{i:05d}.jpg", nrow=1)
                generator.train()

        if epoch % args.snapshot_interval == 0:
            torch.save({"epoch": epoch, "generator": generator.state_dict(), "discriminator": discriminator.state_dict(),
                        "g_optimizer": g_optimizer.state_dict(), "d_optimizer": d_optimizer.state_dict()},
                       f"{args.output_dir}/snapshot_epoch_{epoch}.pth")
            export_onnx(generator, f"{args.output_dir}/generator_epoch_{epoch}.onnx", width, height)
            print(f"epoch {epoch}: snapshot + ONNX saved")


if __name__ == "__main__":
    main()
