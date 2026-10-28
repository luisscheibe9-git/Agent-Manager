"""Draws inbox.ico: 6-colour pinwheel, a fusion of Claude's burst and ChatGPT's six-lobed knot. Run: python make_icon.py"""
from PIL import Image, ImageDraw

S = 1024
BG = (17, 17, 20, 255)
COLORS = [(249, 115, 22), (234, 179, 8), (22, 163, 74), (37, 99, 235), (147, 51, 234), (236, 72, 153)]

im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(im).rounded_rectangle([40, 40, S - 40, S - 40], radius=230, fill=BG)
for i, col in enumerate(COLORS):
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    # capsule pointing up, shifted sideways of centre so the six interlock like a pinwheel
    d.rounded_rectangle([S // 2 - 85 + 70, 140, S // 2 + 85 + 70, 560], radius=85, fill=col + (255,))
    im.alpha_composite(layer.rotate(-60 * i, center=(S // 2, S // 2), resample=Image.BICUBIC))
import io, struct
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
pngs = []
for n in SIZES:  # each size resampled from the 1024 master with LANCZOS, stored as PNG
    buf = io.BytesIO(); im.resize((n, n), Image.LANCZOS).save(buf, "PNG"); pngs.append(buf.getvalue())
head = struct.pack("<HHH", 0, 1, len(SIZES)); off = 6 + 16 * len(SIZES); table = b""
for n, p in zip(SIZES, pngs):
    table += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(p), off); off += len(p)
open("inbox.ico", "wb").write(head + table + b"".join(pngs))
im.resize((512, 512), Image.LANCZOS).save("inbox_512.png")

