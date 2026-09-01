"""Train pix2pix (CCM variant) on a folder of paired images and export ONNX.

Pairs: left half = target, right half = input. Same architecture and training
recipe as figmentapp/pix2pix `train_pix2pix_ccm.ipynb`, so the ONNX loads in
Figment's ONNX Image Model node.

  uv run scripts/train_pix2pix.py DATASET_DIR OUTPUT_DIR --epochs 100
"""

import argparse
import glob
import os
import random
import sys
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
import torchvision.transforms.functional as TF
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.utils import save_image
from tqdm import tqdm

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class Pix2PixDataset(Dataset):
    def __init__(self, root_dir, transform=None, jitter_size=60):
        self.root_dir = root_dir
        self.transform = transform
        self.jitter_size = jitter_size
        self.image_files = sorted(f for f in os.listdir(root_dir) if f.endswith((".jpg", ".png")))

    def __len__(self):
        return len(self.image_files)

    def random_jitter(self, input_image, target_image):
        w, h = input_image.size
        size = [h + self.jitter_size, w + self.jitter_size]
        input_image = TF.resize(input_image, size, interpolation=TF.InterpolationMode.BICUBIC)
        target_image = TF.resize(target_image, size, interpolation=TF.InterpolationMode.BICUBIC)
        i, j, ch, cw = transforms.RandomCrop.get_params(input_image, output_size=(h, w))
        input_image = TF.crop(input_image, i, j, ch, cw)
        target_image = TF.crop(target_image, i, j, ch, cw)
        if random.random() > 0.5:
            input_image = TF.hflip(input_image)
            target_image = TF.hflip(target_image)
        return input_image, target_image

    def __getitem__(self, idx):
        image = Image.open(os.path.join(self.root_dir, self.image_files[idx])).convert("RGB")
        w, h = image.size
        target_image = image.crop((0, 0, w // 2, h))
        input_image = image.crop((w // 2, 0, w, h))
        input_image, target_image = self.random_jitter(input_image, target_image)
        if self.transform:
            input_image = self.transform(input_image)
            target_image = self.transform(target_image)
        return input_image, target_image


class UNetBlock(nn.Module):
    def __init__(self, in_channels, out_channels, down=True, bn=True, dropout=False):
        super().__init__()
        self.conv = (
            nn.Conv2d(in_channels, out_channels, 4, 2, 1, bias=False)
            if down
            else nn.ConvTranspose2d(in_channels, out_channels, 4, 2, 1, bias=False)
        )
        self.bn = nn.InstanceNorm2d(out_channels, affine=True) if bn else None
        self.dropout = nn.Dropout(0.5) if dropout else None
        self.act = nn.LeakyReLU(0.2) if down else nn.ReLU()

    def forward(self, x):
        x = self.conv(x)
        if self.bn:
            x = self.bn(x)
        if self.dropout:
            x = self.dropout(x)
        return self.act(x)


class Generator(nn.Module):
    def __init__(self):
        super().__init__()
        self.down1 = UNetBlock(3, 64, down=True, bn=False)
        self.down2 = UNetBlock(64, 128)
        self.down3 = UNetBlock(128, 256)
        self.down4 = UNetBlock(256, 512)
        self.down5 = UNetBlock(512, 512)
        self.down6 = UNetBlock(512, 512)
        self.down7 = UNetBlock(512, 512)
        self.down8 = UNetBlock(512, 512, bn=False)
        self.up1 = UNetBlock(512, 512, down=False, dropout=True)
        self.up2 = UNetBlock(1024, 512, down=False, dropout=True)
        self.up3 = UNetBlock(1024, 512, down=False, dropout=True)
        self.up4 = UNetBlock(1024, 512, down=False)
        self.up5 = UNetBlock(1024, 256, down=False)
        self.up6 = UNetBlock(512, 128, down=False)
        self.up7 = UNetBlock(256, 64, down=False)
        self.final = nn.Sequential(nn.ConvTranspose2d(128, 3, 4, 2, 1), nn.Tanh())

    def forward(self, x):
        d1 = self.down1(x)
        d2 = self.down2(d1)
        d3 = self.down3(d2)
        d4 = self.down4(d3)
        d5 = self.down5(d4)
        d6 = self.down6(d5)
        d7 = self.down7(d6)
        d8 = self.down8(d7)
        u1 = self.up1(d8)
        u2 = self.up2(torch.cat([u1, d7], 1))
        u3 = self.up3(torch.cat([u2, d6], 1))
        u4 = self.up4(torch.cat([u3, d5], 1))
        u5 = self.up5(torch.cat([u4, d4], 1))
        u6 = self.up6(torch.cat([u5, d3], 1))
        u7 = self.up7(torch.cat([u6, d2], 1))
        return self.final(torch.cat([u7, d1], 1))


class Discriminator(nn.Module):
    def __init__(self):
        super().__init__()
        self.model = nn.Sequential(
            UNetBlock(6, 64, bn=False),
            UNetBlock(64, 128),
            UNetBlock(128, 256),
            UNetBlock(256, 512),
            nn.Conv2d(512, 1, 4, 1, 1),
        )

    def forward(self, x, y):
        return self.model(torch.cat([x, y], dim=1))


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
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--sample-interval", type=int, default=200)
    ap.add_argument("--snapshot-interval", type=int, default=1)
    ap.add_argument("--restart", action="store_true", help="ignore existing snapshots")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    log_path = os.path.join(args.output_dir, "training_log.txt")
    transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.5,) * 3, (0.5,) * 3)])
    dataset = Pix2PixDataset(args.input_dir, transform=transform)
    dataloader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, num_workers=args.workers, drop_last=True)
    sample = dataset[0][0]
    height, width = sample.shape[1], sample.shape[2]
    print(f"{len(dataset)} pairs, input {width}x{height}")

    generator = Generator().to(device)
    discriminator = Discriminator().to(device)
    criterion_gan = nn.BCEWithLogitsLoss()
    criterion_pixel = nn.L1Loss()
    ccm_loss_fn = nn.MSELoss()
    g_optimizer = optim.Adam(generator.parameters(), lr=2e-4, betas=(0.5, 0.999))
    d_optimizer = optim.Adam(discriminator.parameters(), lr=1e-4, betas=(0.5, 0.999))

    fixed_input, fixed_target = (t[:4] for t in next(iter(dataloader)))

    start_epoch = 1
    snapshot = None if args.restart else latest(os.path.join(args.output_dir, "snapshot_epoch_*.pth"))
    if snapshot:
        ck = torch.load(snapshot, map_location=device, weights_only=False)
        generator.load_state_dict(ck["generator"])
        discriminator.load_state_dict(ck["discriminator"])
        g_optimizer.load_state_dict(ck["g_optimizer"])
        d_optimizer.load_state_dict(ck["d_optimizer"])
        start_epoch = int(Path(snapshot).stem.split("_")[2]) + 1
        print(f"Resuming from epoch {start_epoch - 1}")

    for epoch in range(start_epoch, start_epoch + args.epochs):
        for i, (input_img, target_img) in enumerate(tqdm(dataloader, file=sys.stdout, desc=f"epoch {epoch}")):
            input_img, target_img = input_img.to(device), target_img.to(device)

            noise_std = max(0.05, 0.3 * (1 - epoch / args.epochs))
            d_input_real = target_img + torch.randn_like(target_img) * noise_std
            d_input_fake = generator(input_img).detach() + torch.randn_like(target_img) * noise_std
            d_optimizer.zero_grad()
            d_real = discriminator(input_img, d_input_real)
            d_fake = discriminator(input_img, d_input_fake)
            d_loss = (criterion_gan(d_real, torch.full_like(d_real, 0.9)) + criterion_gan(d_fake, torch.zeros_like(d_fake))) / 2
            d_loss.backward()
            d_optimizer.step()

            g_optimizer.zero_grad()
            fake_img = generator(input_img)
            d_fake = discriminator(input_img, fake_img)
            g_loss_gan = criterion_gan(d_fake, torch.ones_like(d_fake))
            g_loss_pixel = criterion_pixel(fake_img, target_img) * 100
            fake_perturbed = generator(input_img + torch.randn_like(input_img) * 0.2)
            ccm_loss = ccm_loss_fn(fake_img, fake_perturbed.detach())
            lambda_ccm = min(50.0, 10.0 + epoch * 0.5)
            g_loss = g_loss_gan + g_loss_pixel + lambda_ccm * ccm_loss
            g_loss.backward()
            g_optimizer.step()

            if i % 10 == 0:
                msg = (f"Epoch {epoch} iter {i} | d_loss: {d_loss.item():.4f} | g_loss: {g_loss.item():.4f} | "
                       f"g_gan: {g_loss_gan.item():.4f} | g_pix: {g_loss_pixel.item():.4f} | ccm: {ccm_loss.item():.4f}")
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
            torch.save({"generator": generator.state_dict(), "discriminator": discriminator.state_dict(),
                        "g_optimizer": g_optimizer.state_dict(), "d_optimizer": d_optimizer.state_dict()},
                       f"{args.output_dir}/snapshot_epoch_{epoch}.pth")
            export_onnx(generator, f"{args.output_dir}/generator_epoch_{epoch}.onnx", width, height)
            print(f"epoch {epoch}: snapshot + ONNX saved")


if __name__ == "__main__":
    main()
