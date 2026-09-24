"""Classical-CV similarity scores between two signature images.

WHAT THIS IS
    Seven descriptive scores in [0,1], 1 = similar, 0 = dissimilar. They exist
    to *explain* a comparison to a human, not to decide it.

WHAT THIS IS NOT
    This module is a pure function of (reference_bgr, test_bgr). It is imported
    by model_service.verify() *after* the verdict fields are computed, it
    returns a dict that is attached under its own key, and it has no reference
    to the model, the threshold, the distance or the verdict object. Nothing
    here can move `is_genuine`, `is_borderline` or `confidence`. There is a
    regression test (tests/test_verdict_isolation.py) that fails if that ever
    stops being true.

WHY IT DOES ITS OWN PREPROCESSING
    It deliberately does NOT reuse the model's 155x155 input, because that
    pipeline destroys the very signals several of these features measure:
      - _deskew() rotates every signature to a canonical angle, so slant
        measured there describes the deskewer, not the writer;
      - _crop_and_pad() rescales the longest side to 155 and pads to a square,
        so absolute size is gone;
      - _normalize_stroke_width() skeletonizes then dilates every stroke to
        exactly 2px, so stroke thickness carries no information at all.
    Computing on that image would produce features with no signal to measure -
    the exact failure mode this rebuild exists to avoid. Instead everything is
    derived from the full-resolution crop the user drew.

DELIBERATELY NOT IMPLEMENTED
    Pen pressure, pen lift, speed/rhythm and tremor. A static photo carries no
    temporal signal, and ink density is confounded by pen, paper and exposure.
    They are omitted rather than reported as a passing score.

ON THE NUMBERS
    The normalization constants below are uncalibrated: they set the scale of
    each score, not its meaning. Compare scores between pairs, not against an
    absolute bar, and do not derive thresholds from them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from scipy.stats import wasserstein_distance
from skimage.morphology import skeletonize

log = logging.getLogger(__name__)

# Work size: far larger than the model's 155px so stroke, slant and spacing
# detail survive, but bounded so skeletonization stays quick.
WORK_MAX_DIM = 1200
# Half-scales for turning an unbounded distance into a [0,1] score, measured
# on CEDAR (36 same-writer and 60 different-writer pairs): each is the MEDIAN
# distance for a different-writer pair, so that pair type lands near 0.5 and
# identical input lands at 1.0. They set the scale of a score, not its meaning
# - do not read them as thresholds.
#
# Guessed constants are what broke this before: the first draft used 1.5 for
# the shape distance, where real pairs sit at 4-6, so letter_formation scored
# 0.000 for every non-identical signature - a feature failing 100% of the time
# regardless of the true match.
SHAPE_D0 = 6.4       # cv2.matchShapes I2 (best separating of I1/I2/I3)
CURVE_D0 = 0.59      # Wasserstein between self-normalized curvature samples
TERMINAL_D0 = 43.0   # degrees, between terminal-angle distributions
ORIENT_BINS = 16
MIN_COMPONENT_AREA_FRAC = 5e-5

FEATURE_ORDER = (
    "letter_formation",
    "line_quality",
    "stroke_direction",
    "size_proportion",
    "alignment_slant",
    "terminal_strokes",
    "proportion_spacing",
)


@dataclass(frozen=True)
class SignatureShape:
    """Everything the seven features need, derived once per image."""

    mask: np.ndarray          # uint8 0/255, ink = 255
    skeleton: np.ndarray      # bool, 1px centreline
    contours: list            # external contours of the mask
    components: list          # (x, y, w, h, area) left-to-right


def _clip01(value: float) -> float:
    if not np.isfinite(value):
        return 0.0
    return float(np.clip(value, 0.0, 1.0))


def _similarity(distance: float, half_scale: float) -> float:
    """Distance -> score, via 1 / (1 + d/d0).

    Reciprocal rather than `1 - d/scale` on purpose: it is monotone and bounded
    but never reaches 0, so a mis-set constant can degrade a score without
    pinning it to zero for every input. Identical -> 1.0, d == d0 -> 0.5.
    """
    if not np.isfinite(distance) or distance < 0:
        return 0.0
    return _clip01(1.0 / (1.0 + distance / half_scale))


def prepare(bgr: np.ndarray) -> SignatureShape | None:
    """grayscale -> Otsu -> binarize -> skeleton, plus contours and components.

    Returns None when the crop holds no usable ink, so callers can omit the
    section rather than report scores computed from noise.
    """
    if bgr is None or bgr.size == 0:
        return None
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    h, w = gray.shape[:2]
    scale = min(1.0, WORK_MAX_DIM / max(h, w))
    if scale < 1.0:
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    # Otsu on a blurred copy: ink is dark, so invert to make ink the foreground.
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Drop specks; they dominate component counts and endpoint statistics.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_area = max(20.0, MIN_COMPONENT_AREA_FRAC * mask.size)
    keep = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_area]
    if not keep:
        return None
    mask = np.where(np.isin(labels, keep), 255, 0).astype(np.uint8)

    skeleton = skeletonize(mask > 0)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    components = sorted(
        (
            (
                int(stats[i, cv2.CC_STAT_LEFT]),
                int(stats[i, cv2.CC_STAT_TOP]),
                int(stats[i, cv2.CC_STAT_WIDTH]),
                int(stats[i, cv2.CC_STAT_HEIGHT]),
                int(stats[i, cv2.CC_STAT_AREA]),
            )
            for i in keep
        ),
        key=lambda c: c[0],
    )
    if not contours:
        return None
    return SignatureShape(mask=mask, skeleton=skeleton, contours=list(contours), components=components)


# --------------------------------------------------------------------------
# skeleton helpers
# --------------------------------------------------------------------------
_NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _neighbour_count(skel: np.ndarray) -> np.ndarray:
    padded = np.pad(skel.astype(np.uint8), 1)
    total = np.zeros_like(skel, dtype=np.uint8)
    for dy, dx in _NEIGHBOURS:
        total += padded[1 + dy : 1 + dy + skel.shape[0], 1 + dx : 1 + dx + skel.shape[1]]
    return total * skel


def _walk_paths(skel: np.ndarray, max_paths: int = 60) -> list[np.ndarray]:
    """Trace strokes from endpoints until a junction or a dead end.

    Not a full graph decomposition - loops with no endpoint are skipped - but
    enough to sample curvature and terminal direction along real strokes.
    """
    counts = _neighbour_count(skel)
    endpoints = list(zip(*np.where(counts == 1)))
    visited = np.zeros_like(skel, dtype=bool)
    paths: list[np.ndarray] = []

    for start in endpoints[:max_paths]:
        if visited[start]:
            continue
        path = [start]
        visited[start] = True
        current = start
        while True:
            nxt = None
            for dy, dx in _NEIGHBOURS:
                y, x = current[0] + dy, current[1] + dx
                if 0 <= y < skel.shape[0] and 0 <= x < skel.shape[1] and skel[y, x] and not visited[y, x]:
                    nxt = (y, x)
                    break
            if nxt is None:
                break
            visited[nxt] = True
            path.append(nxt)
            current = nxt
            if counts[nxt] > 2:  # junction: stop, this stroke ends here
                break
        if len(path) >= 8:
            paths.append(np.array(path, dtype=np.float64))
    return paths


def _curvatures(paths: list[np.ndarray]) -> np.ndarray:
    """Magnitude of the second derivative along each traced stroke."""
    values: list[float] = []
    for path in paths:
        if len(path) < 5:
            continue
        smooth = cv2.GaussianBlur(path.astype(np.float32), (1, 5), 0).reshape(-1, 2)
        d1 = np.diff(smooth, axis=0)
        d2 = np.diff(d1, axis=0)
        values.extend(np.linalg.norm(d2, axis=1).tolist())
    return np.asarray(values, dtype=np.float64)


def _histogram_distance(a: np.ndarray, b: np.ndarray) -> float | None:
    """Wasserstein distance between two samples, each self-normalized first."""
    if a.size < 10 or b.size < 10:
        return None
    # Self-relative: divide by each signature's own median, so the comparison is
    # about the *shape* of the distribution, not the absolute pixel scale.
    a_scale = np.median(a) or 1.0
    b_scale = np.median(b) or 1.0
    return float(wasserstein_distance(a / a_scale, b / b_scale))


# --------------------------------------------------------------------------
# the seven features
# --------------------------------------------------------------------------
def _letter_formation(ref: SignatureShape, test: SignatureShape) -> float | None:
    """Hu-moment shape agreement between the two contour sets."""
    a = sorted(ref.contours, key=cv2.contourArea, reverse=True)[:8]
    b = sorted(test.contours, key=cv2.contourArea, reverse=True)[:8]
    if not a or not b:
        return None
    costs = []
    for contour in a:
        best = min(cv2.matchShapes(contour, other, cv2.CONTOURS_MATCH_I2, 0.0) for other in b)
        costs.append(best)
    return _similarity(float(np.mean(costs)), SHAPE_D0)


def _line_quality(ref: SignatureShape, test: SignatureShape) -> float | None:
    """Agreement between the two curvature (smoothness) distributions."""
    distance = _histogram_distance(_curvatures(_walk_paths(ref.skeleton)),
                                   _curvatures(_walk_paths(test.skeleton)))
    return None if distance is None else _similarity(distance, CURVE_D0)


def _orientation_histogram(mask: np.ndarray) -> np.ndarray | None:
    gx = cv2.Sobel(mask, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(mask, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.hypot(gx, gy)
    if magnitude.sum() <= 0:
        return None
    angles = (np.degrees(np.arctan2(gy, gx)) % 180.0)
    hist, _ = np.histogram(angles, bins=ORIENT_BINS, range=(0.0, 180.0), weights=magnitude)
    norm = np.linalg.norm(hist)
    return None if norm == 0 else hist / norm


def _stroke_direction(ref: SignatureShape, test: SignatureShape) -> float | None:
    a = _orientation_histogram(ref.mask)
    b = _orientation_histogram(test.mask)
    if a is None or b is None:
        return None
    return _clip01(float(np.dot(a, b)))  # both unit-norm: dot == cosine


def _size_proportion(ref: SignatureShape, test: SignatureShape) -> float | None:
    def metrics(shape: SignatureShape) -> tuple[float, float] | None:
        ys, xs = np.where(shape.mask > 0)
        if xs.size == 0:
            return None
        w = float(xs.max() - xs.min() + 1)
        h = float(ys.max() - ys.min() + 1)
        if w <= 0 or h <= 0:
            return None
        return w / h, float(xs.size) / (w * h)

    a, b = metrics(ref), metrics(test)
    if a is None or b is None:
        return None
    aspect = abs(a[0] - b[0]) / max(a[0], b[0])
    density = abs(a[1] - b[1]) / max(a[1], b[1], 1e-6)
    return _clip01(1.0 - 0.5 * (aspect + density))


def _major_axis_angle(shape: SignatureShape) -> float | None:
    """Angle of the ink cloud's principal axis, in degrees."""
    ys, xs = np.where(shape.mask > 0)
    if xs.size < 20:
        return None
    coords = np.column_stack([xs - xs.mean(), ys - ys.mean()]).astype(np.float64)
    _, _, vt = np.linalg.svd(coords, full_matrices=False)
    vx, vy = vt[0]
    return float(np.degrees(np.arctan2(vy, vx)))


def _alignment_slant(ref: SignatureShape, test: SignatureShape) -> float | None:
    a, b = _major_axis_angle(ref), _major_axis_angle(test)
    if a is None or b is None:
        return None
    diff = abs(a - b) % 180.0
    diff = min(diff, 180.0 - diff)  # axis is undirected
    return _clip01(1.0 - diff / 90.0)


def _terminal_angles(shape: SignatureShape, tail: int = 10) -> np.ndarray:
    """Direction of the last ~`tail` pixels of each stroke, in degrees."""
    angles: list[float] = []
    for path in _walk_paths(shape.skeleton):
        if len(path) < tail:
            continue
        end = path[-1]
        back = path[-min(tail, len(path))]
        dy, dx = end[0] - back[0], end[1] - back[1]
        if dx == 0 and dy == 0:
            continue
        angles.append(float(np.degrees(np.arctan2(dy, dx)) % 360.0))
    return np.asarray(angles, dtype=np.float64)


def _terminal_strokes(ref: SignatureShape, test: SignatureShape) -> float | None:
    a, b = _terminal_angles(ref), _terminal_angles(test)
    if a.size < 3 or b.size < 3:
        return None
    distance = float(wasserstein_distance(a, b))
    return _similarity(distance, TERMINAL_D0)


def _spacing_vector(shape: SignatureShape, length: int = 8) -> np.ndarray | None:
    """Component widths and inter-component gaps, left to right, normalized."""
    comps = shape.components
    if len(comps) < 2:
        return None
    total = float(comps[-1][0] + comps[-1][2] - comps[0][0])
    if total <= 0:
        return None
    widths = [c[2] / total for c in comps]
    gaps = [
        max(0.0, (comps[i + 1][0] - (comps[i][0] + comps[i][2])) / total)
        for i in range(len(comps) - 1)
    ]
    series = np.asarray(widths + gaps, dtype=np.float64)
    # Resample to a fixed length so two signatures with different component
    # counts are still comparable.
    resampled = np.interp(
        np.linspace(0.0, 1.0, length), np.linspace(0.0, 1.0, series.size), series
    )
    norm = np.linalg.norm(resampled)
    return None if norm == 0 else resampled / norm


def _proportion_spacing(ref: SignatureShape, test: SignatureShape) -> float | None:
    a, b = _spacing_vector(ref), _spacing_vector(test)
    if a is None or b is None:
        return None
    return _clip01(float(np.dot(a, b)))


_FEATURES = {
    "letter_formation": _letter_formation,
    "line_quality": _line_quality,
    "stroke_direction": _stroke_direction,
    "size_proportion": _size_proportion,
    "alignment_slant": _alignment_slant,
    "terminal_strokes": _terminal_strokes,
    "proportion_spacing": _proportion_spacing,
}


def compare(reference_bgr: np.ndarray, test_bgr: np.ndarray) -> dict[str, Any] | None:
    """Seven similarity scores in [0,1]. Pure: inputs in, numbers out.

    A feature returns None when the image genuinely does not support it (too
    few strokes to trace, one connected component and therefore no spacing).
    None is reported as "not measurable" rather than as a low score, because a
    feature that always fails is indistinguishable from a real mismatch - which
    is precisely how this went wrong before.
    """
    ref = prepare(reference_bgr)
    test = prepare(test_bgr)
    if ref is None or test is None:
        return None

    scores: dict[str, float | None] = {}
    for name in FEATURE_ORDER:
        try:
            scores[name] = _FEATURES[name](ref, test)
        except Exception:  # noqa: BLE001 - a broken feature must not break a comparison
            log.exception("forensic feature %s failed", name)
            scores[name] = None

    measured = [v for v in scores.values() if v is not None]
    return {
        "scores": {k: (round(v, 4) if v is not None else None) for k, v in scores.items()},
        # A mean of the measurable features, for display only. It is NOT fused
        # with the neural score, and nothing downstream reads it.
        "mean_score": round(float(np.mean(measured)), 4) if measured else None,
        "measured": len(measured),
        "total": len(FEATURE_ORDER),
    }
