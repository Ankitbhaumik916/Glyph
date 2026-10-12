"""The exported report must not re-merge the verdict with the advisory section.

The predecessor project's report combined the neural similarity with an
aggregate of the forensic features into one "SWGDOC verdict", and that merged
number overrode verdicts the model had got right. The report in this codebase
exists in the shape it does to make that recombination impossible, so these
tests are about the *document's wording and structure*, not only about it
rendering without raising.

Everything that can be checked without a PDF parser is checked directly
against the pure text helpers, so the core guarantees hold even where pypdf
is not installed.
"""
from __future__ import annotations

import re

import pytest

from app import forensic_features, report

GENUINE = {
    "distance": 0.2871,
    "threshold": 0.393784,
    "max_distance": 2.0,
    "is_genuine": True,
    "is_borderline": False,
    "borderline_band": 0.05,
    "variants": 7,
    "variant_spread": 0.041,
    "confidence": 0.2709,
    "threshold_source": "bundle",
    "bundle_threshold": 0.393784,
    "model_architecture": "SigNetBackbone-GAP",
    "document_type": "Cheque",
    "forensic": {
        "scores": {
            "line_quality": 0.4521,
            "stroke_direction": 0.9782,
            "size_proportion": 0.8901,
            "alignment_slant": 0.7404,
            "proportion_spacing": 0.9018,
        },
        "mean_score": 0.7925,
        "measured": 5,
        "total": 5,
    },
}

BORDERLINE = {**GENUINE, "is_borderline": True, "distance": 0.3801, "confidence": 0.034}
FORGED = {**GENUINE, "is_genuine": False, "distance": 0.6639, "confidence": 0.1681}
NO_CROP = {**GENUINE, "forensic": None, "variants": 1, "variant_spread": 0.0}

ALL_CASES = (GENUINE, BORDERLINE, FORGED, NO_CROP)

# Status words from the old report's per-feature verdict. A feature here gets
# "Measured" / "Not measurable" and nothing else: forensic_features.py is
# explicit that no threshold may be derived from its scores, so a per-row pass
# mark would be the merged verdict again one level down.
VERDICT_WORDS = re.compile(r"\b(PASS|FAIL|WARN|PASSED|FAILED|SWGDOC)\b")


def _text(payload: dict) -> str:
    """Rendered report text. Skips when no PDF parser is available."""
    pypdf = pytest.importorskip("pypdf")
    from io import BytesIO

    reader = pypdf.PdfReader(BytesIO(report.build_pdf(payload)))
    return "\n".join(page.extract_text() for page in reader.pages)


# --- the separation ---------------------------------------------------------

def test_feature_list_tracks_forensic_features():
    """The report must not carry its own idea of which features exist.

    The old report hardcoded nine rows. If a feature is retired in
    forensic_features.py, it has to disappear from the report too, or the
    document reintroduces a measurement the codebase has already rejected.
    """
    assert tuple(report.FEATURE_LABELS) == forensic_features.FEATURE_ORDER
    assert set(report.FEATURE_NOTES) == set(report.FEATURE_LABELS)


def test_every_kept_feature_is_described():
    for key in forensic_features.FEATURE_ORDER:
        assert report.FEATURE_NOTES[key].strip(), f"{key} has no description"


def test_recommendation_comes_only_from_the_model_verdict():
    """No advisory score may change the recommended action."""
    for payload in (GENUINE, BORDERLINE, FORGED):
        baseline = report._recommendation(payload)

        # Same verdict, wildly different advisory scores: identical text.
        for scores in (
            {k: 0.01 for k in forensic_features.FEATURE_ORDER},
            {k: 0.99 for k in forensic_features.FEATURE_ORDER},
            {k: None for k in forensic_features.FEATURE_ORDER},
        ):
            altered = {**payload, "forensic": {"scores": scores, "mean_score": None,
                                               "measured": 0, "total": 5}}
            assert report._recommendation(altered) == baseline

        # And with no advisory section at all.
        assert report._recommendation({**payload, "forensic": None}) == baseline


def test_recommendation_differs_by_verdict():
    """Guards against the above passing because the text is a constant."""
    texts = {report._recommendation(p) for p in (GENUINE, BORDERLINE, FORGED)}
    assert len(texts) == 3


def test_recommendation_states_the_advisory_section_was_not_an_input():
    for payload in (GENUINE, BORDERLINE, FORGED, NO_CROP):
        assert "not an input to it" in report._recommendation(payload)


def test_advisory_flags_never_read_as_a_verdict():
    for payload in ALL_CASES:
        for flag in report._advisory_flags(payload["forensic"]):
            assert not VERDICT_WORDS.search(flag), flag
            lowered = flag.lower()
            for word in ("forgery", "forged", "authentic", "genuine", "inconclusive"):
                assert word not in lowered, f"verdict language in flag: {flag}"


def test_advisory_flags_say_the_section_is_not_evidence():
    joined = " ".join(report._advisory_flags(GENUINE["forensic"])).lower()
    assert "not to support a conclusion" in joined


def test_unmeasurable_feature_is_not_reported_as_a_low_score():
    partial = {"scores": {**GENUINE["forensic"]["scores"], "alignment_slant": None},
               "mean_score": 0.79, "measured": 4, "total": 5}
    joined = " ".join(report._advisory_flags(partial))
    assert "Not measurable for this pair: Alignment & slant" in joined
    assert "not evidence of a difference" in joined


def test_missing_advisory_section_is_explained_not_silent():
    flags = report._advisory_flags(None)
    assert len(flags) == 1
    assert "crop box was not drawn" in flags[0]


def test_model_narrative_uses_only_model_fields():
    """Feeding it no forensic data at all must not change a word."""
    for payload in (GENUINE, BORDERLINE, FORGED):
        stripped = {k: v for k, v in payload.items() if k != "forensic"}
        assert report._model_narrative(stripped) == report._model_narrative(payload)


# --- the document -----------------------------------------------------------

def test_renders_a_pdf_for_every_verdict():
    for payload in ALL_CASES:
        pdf = report.build_pdf(payload)
        assert pdf.startswith(b"%PDF"), "not a PDF"
        assert len(pdf) > 2000


def test_build_pdf_does_not_mutate_its_input():
    """It is a renderer; the caller's result object is not its to edit."""
    import copy

    payload = copy.deepcopy(GENUINE)
    report.build_pdf(payload)
    assert payload == GENUINE


def test_ids_are_fresh_per_export():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    first, second = report.new_ids(now), report.new_ids(now)
    assert first != second
    case_id, report_id = first
    assert case_id.startswith("GLY-")
    assert report_id.startswith("R-")
    # Not the predecessor's scheme (a bare millisecond timestamp).
    assert not case_id.lstrip("GLY-").isdigit()


def test_rendered_text_has_no_pass_fail_verdict_words():
    for payload in ALL_CASES:
        found = VERDICT_WORDS.findall(_text(payload))
        assert not found, f"verdict words in rendered report: {found}"


def test_rendered_text_labels_the_advisory_section():
    text = _text(GENUINE)
    assert "ADVISORY - NOT USED IN VERDICT" in text
    assert "MODEL VERDICT" in text
    assert "did not" in text and "contribute to the distance" in text


def test_rendered_text_keeps_the_two_summary_numbers_apart():
    """A reader must not be able to mistake the advisory mean for a confidence."""
    text = _text(GENUINE)
    assert "not combined with the model margin above" in text
    assert "it is not a confidence" in text
    # The margin is labelled as a distance from the boundary, not a probability.
    assert "not a probability" in text


def test_rendered_text_lists_exactly_the_kept_features_as_rows():
    text = _text(GENUINE)
    for key in forensic_features.FEATURE_ORDER:
        assert report.FEATURE_LABELS[key] in text

    # Retired features may be named once, in the withdrawal note, so a reader
    # comparing against an older report knows they were removed on purpose -
    # but never as a scored row.
    assert "since withdrawn" in text
    for retired in report.RETIRED_FEATURES:
        assert text.count(retired) == 1, f"{retired} appears outside the withdrawal note"


def test_rendered_text_carries_the_status_line_and_disclaimer():
    text = _text(GENUINE)
    assert "BUNDLE DEFAULT" in text
    assert "threshold 0.3938" in text
    assert "SigNetBackbone-GAP" in text
    assert "not the opinion of a qualified forensic document" in text
    assert "no evidentiary standing" in text
    assert "0.17-0.23" in text  # the real error rate, stated to the reader


def test_calibrated_threshold_is_reported_as_such():
    text = _text({**GENUINE, "threshold_source": "calibrated",
                  "threshold": 0.42, "bundle_threshold": 0.393784})
    assert "CALIBRATED" in text
    assert "bundle default was 0.3938" in text
