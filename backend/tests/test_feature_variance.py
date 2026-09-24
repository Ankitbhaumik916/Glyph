"""No feature may silently collapse to a constant.

This is the general guard for a failure that has now happened twice while
building this module:

  1. a guessed scale constant pinned letter_formation to 0.000 for every
     non-identical pair;
  2. a component-merge threshold collapsed every signature to one component,
     making proportion_spacing unmeasurable for every pair.

Both were invisible to a correctness test - the scores were valid floats in
range, the API worked, the verdict was untouched - and both would have shipped
a feature that reports the same thing no matter what it is shown.

So this runs the whole battery over a fixed synthetic set and asserts, per
feature, that it actually responds to its input: measurable often enough, not
constant, and not pinned to either end of the scale.

The samples are generated here rather than read from disk so the test needs no
dataset and gives the same answer on any machine.
"""
from __future__ import annotations

import itertools

import cv2
import numpy as np
import pytest

from app.forensic_features import FEATURE_ORDER, compare

# Per-feature floors. Deliberately loose: this test is a collapse alarm, not a
# quality bar, and it should only fire when a feature has stopped responding.
MIN_MEASURABLE_FRACTION = 0.6
MIN_STD = 0.01
# A feature must also use a sane part of the scale. Variance alone is not
# enough: with the 1/(1 + d/d0) mapping a mis-set constant no longer pins
# scores to exactly zero, it squashes them into a narrow band just above it
# (measured: setting SHAPE_D0 to 0.4 put every pair between 0.05 and 0.15),
# which still has enough variance to slip past the collapse alarm while
# rendering as a permanently empty bar.
MIN_MEDIAN = 0.10
MAX_MEDIAN = 0.995
MIN_RANGE = 0.05
WRITERS = 4
SAMPLES_PER_WRITER = 2


def _signature(writer: int, sample: int, size: tuple[int, int] = (420, 1100)) -> np.ndarray:
    """A deterministic multi-stroke scrawl, styled per writer.

    Two to four stroke groups with gaps between them, so connected-component
    features have something real to segment - a single unbroken polyline would
    make proportion_spacing unmeasurable by construction and hide exactly the
    regression this test exists to catch.
    """
    rng = np.random.default_rng(writer * 1000 + sample)
    height, width = size
    img = np.full((height, width, 3), 242, np.uint8)

    # Writer-specific style: stroke thickness, slant, wave shape, group widths.
    thickness = 3 + writer % 3
    slant = -0.35 + 0.22 * writer
    freq = 7.0 + 2.5 * writer
    amp = 40 + 12 * (writer % 3)

    # Group count and gap width vary per writer: a spacing feature has nothing
    # to distinguish if every fixture is laid out identically, and a uniform
    # fixture would make this test pass for the wrong reason.
    groups = 2 + writer % 3
    gap = 40 + 55 * (writer % 3)

    x = 80
    for group in range(groups):
        span = 170 + 90 * ((writer + group) % 3)
        points = []
        for i in range(160):
            t = i / 159.0
            px = x + int(span * t)
            py = (
                height // 2
                + int(amp * np.sin(t * freq + writer + group))
                + int(slant * span * (t - 0.5))
                + int(rng.normal(0, 1.1))  # sample-to-sample variation
            )
            points.append([px, py])
        cv2.polylines(img, [np.array(points, np.int32)], False, (28, 28, 38), thickness)
        x += span + gap
    return img


@pytest.fixture(scope="module")
def battery() -> dict[str, list[float]]:
    """Every feature's scores over all same- and cross-writer pairs."""
    images = {
        (w, s): _signature(w, s)
        for w in range(WRITERS)
        for s in range(SAMPLES_PER_WRITER)
    }
    values: dict[str, list[float | None]] = {f: [] for f in FEATURE_ORDER}
    for a, b in itertools.combinations(images, 2):
        result = compare(images[a], images[b])
        assert result is not None, f"no ink found for {a} vs {b}"
        for feature in FEATURE_ORDER:
            values[feature].append(result["scores"][feature])
    assert len(next(iter(values.values()))) >= 20, "battery too small to judge variance"
    return values


@pytest.mark.parametrize("feature", FEATURE_ORDER)
def test_feature_is_usually_measurable(battery, feature):
    """A feature that is almost never computable is a broken feature."""
    values = battery[feature]
    measured = [v for v in values if v is not None]
    fraction = len(measured) / len(values)
    assert fraction >= MIN_MEASURABLE_FRACTION, (
        f"{feature} was measurable for only {fraction:.0%} of pairs "
        f"({len(measured)}/{len(values)}) - it has stopped responding to its input"
    )


@pytest.mark.parametrize("feature", FEATURE_ORDER)
def test_feature_variance_has_not_collapsed(battery, feature):
    """The alarm itself: a feature returning one value tells you nothing."""
    measured = [v for v in battery[feature] if v is not None]
    spread = float(np.std(measured))
    assert spread >= MIN_STD, (
        f"{feature} has collapsed to a near-constant {np.mean(measured):.3f} "
        f"(std {spread:.4f}) across {len(measured)} pairs"
    )


@pytest.mark.parametrize("feature", FEATURE_ORDER)
def test_feature_is_not_pinned_to_an_extreme(battery, feature):
    """Catches the original bug shape: every real pair scoring exactly 0 or 1."""
    measured = [v for v in battery[feature] if v is not None]
    assert not all(v <= 0.001 for v in measured), f"{feature} is pinned at 0 for every pair"
    assert not all(v >= 0.999 for v in measured), f"{feature} is pinned at 1 for every pair"


@pytest.mark.parametrize("feature", FEATURE_ORDER)
def test_feature_uses_a_reasonable_part_of_the_scale(battery, feature):
    """Catches a mis-set scale constant, which squashes rather than pins."""
    measured = [v for v in battery[feature] if v is not None]
    median = float(np.median(measured))
    spread = max(measured) - min(measured)
    assert MIN_MEDIAN <= median <= MAX_MEDIAN, (
        f"{feature} has a median of {median:.3f} over {len(measured)} pairs - its "
        "scale constant is mis-set, so it is squashed against one end of the scale"
    )
    assert spread >= MIN_RANGE, (
        f"{feature} spans only {spread:.3f} of the scale across the battery"
    )


def test_scores_stay_in_range(battery):
    for feature, values in battery.items():
        for value in values:
            assert value is None or 0.0 <= value <= 1.0, f"{feature} out of range: {value}"


def test_identical_input_still_scores_one():
    """The other end of the same alarm: a feature that cannot reach 1.0 on a
    signature compared with itself is not measuring similarity at all."""
    img = _signature(1, 0)
    result = compare(img, img.copy())
    assert result is not None
    measured = {k: v for k, v in result["scores"].items() if v is not None}
    assert len(measured) >= len(FEATURE_ORDER) - 1, f"only {len(measured)} features measurable"
    for name, value in measured.items():
        assert value > 0.98, f"{name} scored {value} comparing a signature with itself"
