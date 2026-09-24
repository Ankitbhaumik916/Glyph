"""The verdict must not depend on the supporting visual analysis.

This is the regression test that stops forensic_features.py quietly becoming a
gate again. It asserts that every verdict field is byte-identical whether the
analysis runs, is switched off, or raises - for a high-similarity pair and a
low-similarity pair.

Run from backend/:  python -m pytest tests -v
"""
from __future__ import annotations

import io
import json

import cv2
import numpy as np
import pytest

from app import config
from app.cropping import CropBox
from app.model_service import verifier

# Everything the verdict is made of. `forensic` is deliberately excluded: it is
# the additive key under test.
VERDICT_FIELDS = (
    "distance",
    "threshold",
    "max_distance",
    "is_genuine",
    "is_borderline",
    "borderline_band",
    "variants",
    "variant_spread",
    "confidence",
    "preprocessed_ref_base64",
    "preprocessed_test_base64",
)

FULL_BOX = CropBox(x=0.0, y=0.0, width=1.0, height=1.0)


def _signature_png(seed: int, wobble: float = 0.0) -> bytes:
    """A synthetic signature-like scrawl on paper, as encoded image bytes."""
    rng = np.random.default_rng(seed)
    img = np.full((360, 900, 3), 240, np.uint8)
    points = []
    for i in range(420):
        t = i / 420.0
        x = 90 + int(720 * t)
        y = 180 + int(70 * np.sin(t * 9 + seed)) + int(35 * np.sin(t * 4 + seed * 2))
        if wobble:
            y += int(rng.normal(0, wobble))
        points.append([x, y])
    cv2.polylines(img, [np.array(points, np.int32)], False, (30, 30, 40), 4)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


@pytest.fixture(scope="module", autouse=True)
def loaded_model():
    if not verifier.is_ready:
        verifier.load()
    return verifier


@pytest.fixture(scope="module")
def pairs():
    """One high-similarity pair and one low-similarity pair."""
    same = _signature_png(1)
    return {
        "high": (same, _signature_png(1, wobble=1.2)),
        "low": (same, _signature_png(7)),
    }


def _verdict_only(result: dict) -> str:
    return json.dumps({k: result[k] for k in VERDICT_FIELDS}, sort_keys=True)


@pytest.mark.parametrize("case", ["high", "low"])
def test_verdict_identical_with_and_without_analysis(pairs, case, monkeypatch):
    ref, test = pairs[case]

    monkeypatch.setattr(config, "FORENSIC_ENABLED", True)
    with_analysis = verifier.verify(ref, test, FULL_BOX, FULL_BOX)

    monkeypatch.setattr(config, "FORENSIC_ENABLED", False)
    without_analysis = verifier.verify(ref, test, FULL_BOX, FULL_BOX)

    assert _verdict_only(with_analysis) == _verdict_only(without_analysis)
    # ...and the analysis really did run in the first case, so this is not
    # passing simply because both runs skipped it.
    assert with_analysis["forensic"] is not None
    assert without_analysis["forensic"] is None


@pytest.mark.parametrize("case", ["high", "low"])
def test_verdict_survives_a_broken_analysis(pairs, case, monkeypatch):
    """A crash inside the analysis must not change or break the verdict."""
    ref, test = pairs[case]
    monkeypatch.setattr(config, "FORENSIC_ENABLED", True)
    healthy = verifier.verify(ref, test, FULL_BOX, FULL_BOX)

    import app.forensic_features as ff

    def explode(*_args, **_kwargs):
        raise RuntimeError("deliberate failure")

    monkeypatch.setattr(ff, "compare", explode)
    broken = verifier.verify(ref, test, FULL_BOX, FULL_BOX)

    assert _verdict_only(healthy) == _verdict_only(broken)
    assert broken["forensic"] is None


def test_high_and_low_cases_really_differ(pairs):
    """Guards the test itself: two identical verdicts would make it vacuous."""
    high = verifier.verify(*pairs["high"], FULL_BOX, FULL_BOX)
    low = verifier.verify(*pairs["low"], FULL_BOX, FULL_BOX)
    assert high["distance"] < low["distance"]


def test_scores_are_bounded_and_named(pairs):
    from app.forensic_features import FEATURE_ORDER

    result = verifier.verify(*pairs["high"], FULL_BOX, FULL_BOX)
    forensic = result["forensic"]
    assert set(forensic["scores"]) == set(FEATURE_ORDER)
    for name, value in forensic["scores"].items():
        assert value is None or 0.0 <= value <= 1.0, f"{name} out of range: {value}"


def test_identical_images_score_one():
    """A feature that cannot reach 1.0 on identical input has no signal."""
    from app.forensic_features import compare

    img = cv2.imdecode(np.frombuffer(_signature_png(3), np.uint8), cv2.IMREAD_COLOR)
    result = compare(img, img.copy())
    assert result is not None
    measured = {k: v for k, v in result["scores"].items() if v is not None}
    assert measured, "no feature was measurable on a clean synthetic signature"
    for name, value in measured.items():
        assert value > 0.98, f"{name} scored {value} on identical input"


def test_no_forensic_without_a_crop_box(pairs):
    """Without a drawn box the analysis would be measuring paper, not ink."""
    ref, test = pairs["high"]
    assert verifier.verify(ref, test, None, None)["forensic"] is None
