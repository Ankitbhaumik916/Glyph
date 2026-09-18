"""User crop handling.

A user-drawn box only has to do one job: exclude clutter (cloth, fingers,
shadows) that fools the automatic document/signature localizer. Its exact size
and aspect ratio must NOT influence the result - but the preprocessing pipeline
is sensitive to both (the 350px downsample factor and the Hough deskew's
minLineLength scale with image size). So after cropping we re-tighten to the
ink itself with a fixed proportional margin and a fixed output size, making
differently drawn boxes around the same signature produce the same input.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import cv2
import numpy as np
from skimage.filters import threshold_sauvola

from .errors import ImageDecodeError

# Proportional padding around the ink bounding box, relative to its longer side.
CANONICAL_MARGIN = 0.10
# Longest side of the canonical crop. Equals the preprocessor's early-downsample
# size, so its own resize becomes a no-op and scale is fully determined here.
CANONICAL_MAX_DIM = 350
# Resolution the ink search runs at; plenty for a bounding box.
_SEARCH_MAX_DIM = 1000


@dataclass(frozen=True)
class CropBox:
    """Normalized [0,1] rectangle in the EXIF-oriented image frame."""

    x: float
    y: float
    width: float
    height: float


def parse_crop(raw: str | None, field: str) -> CropBox | None:
    """Parse the JSON crop form field. Empty/missing means no crop."""
    if raw is None or not raw.strip():
        return None
    try:
        data = json.loads(raw)
        box = CropBox(
            x=float(data["x"]),
            y=float(data["y"]),
            width=float(data["width"]),
            height=float(data["height"]),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ImageDecodeError(
            f"The {field} crop is malformed.",
            field=field,
            hint='Expected JSON like {"x":0.1,"y":0.2,"width":0.5,"height":0.3} in 0-1 units.',
        ) from exc

    values = (box.x, box.y, box.width, box.height)
    if not all(np.isfinite(v) for v in values):
        raise ImageDecodeError(f"The {field} crop contains invalid numbers.", field=field)
    if box.width <= 0 or box.height <= 0:
        raise ImageDecodeError(f"The {field} crop box is empty.", field=field)
    return box


def apply_crop(bgr: np.ndarray, box: CropBox, field: str) -> np.ndarray:
    """Cut the box out of the full-resolution image (clamped to its bounds)."""
    h, w = bgr.shape[:2]
    x0 = int(np.clip(round(box.x * w), 0, w))
    y0 = int(np.clip(round(box.y * h), 0, h))
    x1 = int(np.clip(round((box.x + box.width) * w), 0, w))
    y1 = int(np.clip(round((box.y + box.height) * h), 0, h))
    if x1 - x0 < 16 or y1 - y0 < 16:
        raise ImageDecodeError(
            f"The {field} crop is too small to analyse.",
            field=field,
            hint="Draw a larger box around the whole signature.",
        )
    return np.ascontiguousarray(bgr[y0:y1, x0:x1])


@dataclass(frozen=True)
class InkBox:
    """Bounding box of the ink in an image, plus the paper colour around it."""

    x0: float
    y0: float
    x1: float
    y1: float
    paper: list[int]


def find_ink_box(bgr: np.ndarray) -> InkBox | None:
    """Locate the signature strokes. None when the image holds no ink.

    Split out from `canonicalize` so several margins can be rendered from one
    search - the Sauvola pass and connected components dominate the cost.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    scale = min(1.0, _SEARCH_MAX_DIM / max(h, w))
    small = (
        cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
        if scale < 1.0
        else gray
    )

    # Same binarization family as the pipeline, so "ink" means the same thing.
    ink = (small < threshold_sauvola(small, window_size=25, k=0.2)).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    min_area = max(12, 5e-5 * small.size)
    keep = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_area]
    if not keep:
        return None

    mask = np.isin(labels, keep)
    ys, xs = np.where(mask)

    # Paper colour = median of non-ink pixels. Used for padding, never
    # replicated edges, which would smear any stroke touching the border.
    full_mask = cv2.resize(mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
    background = bgr[~full_mask]
    paper = [int(v) for v in np.median(background, axis=0)] if background.size else [255, 255, 255]

    return InkBox(
        x0=xs.min() / scale,
        y0=ys.min() / scale,
        x1=(xs.max() + 1) / scale,
        y1=(ys.max() + 1) / scale,
        paper=paper,
    )


def render_at_margin(bgr: np.ndarray, box: InkBox, margin: float) -> np.ndarray:
    """Cut `box` out of the image with `margin` padding, at the canonical size."""
    h, w = bgr.shape[:2]
    pad = margin * max(box.x1 - box.x0, box.y1 - box.y0)
    X0, Y0 = int(round(box.x0 - pad)), int(round(box.y0 - pad))
    X1, Y1 = int(round(box.x1 + pad)), int(round(box.y1 + pad))

    paper = box.paper
    top, left = max(0, -Y0), max(0, -X0)
    bottom, right = max(0, Y1 - h), max(0, X1 - w)
    padded = cv2.copyMakeBorder(bgr, top, bottom, left, right, cv2.BORDER_CONSTANT, value=paper)
    out = padded[Y0 + top : Y1 + top, X0 + left : X1 + left]

    k = CANONICAL_MAX_DIM / max(out.shape[:2])
    size = (max(1, int(round(out.shape[1] * k))), max(1, int(round(out.shape[0] * k))))
    return cv2.resize(out, size, interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)


def canonicalize(bgr: np.ndarray, margin: float = CANONICAL_MARGIN) -> np.ndarray:
    """Re-crop to the ink with a fixed margin and rescale to a fixed size.

    Returns the input unchanged if no ink is found; the pipeline's own
    no-signature check then reports it.
    """
    box = find_ink_box(bgr)
    return bgr if box is None else render_at_margin(bgr, box, margin)
