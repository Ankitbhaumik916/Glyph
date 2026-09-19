"""Turn the supplied logo JPEG into clean brand assets.

The source is a black isometric cube with white internal lines on a light grey
plate. Those internal lines are nearly the same tone as the background, so a
plain threshold would punch holes through the mark. Instead the OUTER
background is found by flood-filling from the corners, and everything the fill
never reaches is the logo.

Outputs (all square, transparent, trimmed then re-padded):
  mark-dark.png   original artwork - for light surfaces
  mark-light.png  inverted         - for dark surfaces (the app's default)
  icon.png        black mark on an opaque light plate - browser tab, any theme
"""
import pathlib
import numpy as np
import cv2
from PIL import Image

SRC = str(pathlib.Path(__file__).with_name("logo-source.jpeg"))
OUT = str(pathlib.Path(__file__).resolve().parents[1] / "frontend" / "public" / "brand")
SS = 4          # supersample factor, for clean anti-aliased edges
PAD = 0.06      # margin around the mark, as a fraction of its longest side

import os
os.makedirs(OUT, exist_ok=True)

bgr = cv2.imread(SRC)
h, w = bgr.shape[:2]
big = cv2.resize(bgr, (w * SS, h * SS), interpolation=cv2.INTER_CUBIC)
gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)

# "Light" = background plate and the white lines inside the cube.
light = (gray > 128).astype(np.uint8) * 255

# Flood from every corner: only the plate is reachable from outside.
ff = light.copy()
mask = np.zeros((ff.shape[0] + 2, ff.shape[1] + 2), np.uint8)
for seed in [(0, 0), (ff.shape[1] - 1, 0), (0, ff.shape[0] - 1), (ff.shape[1] - 1, ff.shape[0] - 1)]:
    if ff[seed[1], seed[0]] == 255:
        cv2.floodFill(ff, mask, seed, 128)
outside = ff == 128                       # the plate
logo = (~outside).astype(np.uint8) * 255  # cube body + enclosed white lines

# Tidy specks, then feather by one supersampled pixel so edges resolve smoothly.
logo = cv2.morphologyEx(logo, cv2.MORPH_CLOSE, np.ones((SS, SS), np.uint8))
logo = cv2.morphologyEx(logo, cv2.MORPH_OPEN, np.ones((SS, SS), np.uint8))
alpha = cv2.GaussianBlur(logo, (0, 0), SS * 0.5)

ys, xs = np.where(logo > 0)
y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
side = max(y1 - y0, x1 - x0)
pad = int(side * PAD)
box = side + 2 * pad
cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
top, left = cy - box // 2, cx - box // 2


def crop(arr: np.ndarray) -> np.ndarray:
    """Square crop centred on the mark, zero-padded if it runs off the edge."""
    out = np.zeros((box, box) + arr.shape[2:], arr.dtype)
    sy0, sx0 = max(0, top), max(0, left)
    sy1, sx1 = min(arr.shape[0], top + box), min(arr.shape[1], left + box)
    out[sy0 - top : sy1 - top, sx0 - left : sx1 - left] = arr[sy0:sy1, sx0:sx1]
    return out


a = crop(alpha)
g = crop(gray)
target = 512


def save(rgb: np.ndarray, alpha_ch: np.ndarray, name: str) -> None:
    rgba = np.dstack([rgb, alpha_ch]).astype(np.uint8)
    img = Image.fromarray(rgba, "RGBA").resize((target, target), Image.LANCZOS)
    img.save(f"{OUT}\\{name}")
    print(f"  {name}: {img.size}, {os.path.getsize(f'{OUT}/{name}')} bytes")


# Body is black, lines white: keep as-is for light surfaces.
dark_rgb = np.dstack([g, g, g])
save(dark_rgb, a, "mark-dark.png")

# Inverted for dark surfaces: near-white body, dark lines.
inv = 255 - g
save(np.dstack([inv, inv, inv]), a, "mark-light.png")

# Favicon: black mark on an opaque light plate, so it reads on any tab colour.
plate = np.full(dark_rgb.shape, 232, np.uint8)
af = (a / 255.0)[..., None]
composited = (dark_rgb * af + plate * (1 - af)).astype(np.uint8)
icon = Image.fromarray(composited, "RGB").resize((512, 512), Image.LANCZOS)
# Rounded corners, so it sits well as an app/tab icon.
r = 96
m = Image.new("L", (512, 512), 0)
from PIL import ImageDraw
ImageDraw.Draw(m).rounded_rectangle([0, 0, 511, 511], radius=r, fill=255)
icon.putalpha(m)
icon.save(f"{OUT}\\icon.png")
print(f"  icon.png: {icon.size}, {os.path.getsize(f'{OUT}/icon.png')} bytes")
