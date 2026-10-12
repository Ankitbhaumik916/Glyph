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



def _tiny_png(slant: int = 0) -> str:
    """A 155x155 stand-in for a preprocessed signature.

    `slant` keeps the reference and questioned images from being byte-identical:
    a PDF stores one XObject for two identical images, which would make an
    image-count assertion pass for the wrong reason.
    """
    import base64 as b64
    from io import BytesIO

    from PIL import Image, ImageDraw

    image = Image.new("L", (155, 155), 0)
    ImageDraw.Draw(image).line([(14, 90 + slant), (140, 70 - slant)], fill=255, width=2)
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return b64.b64encode(buffer.getvalue()).decode()


GENUINE_WITH_IMAGES = {
    **GENUINE,
    "preprocessed_ref_base64": _tiny_png(0),
    "preprocessed_test_base64": _tiny_png(9),
}

ALL_CASES = (GENUINE, BORDERLINE, FORGED, NO_CROP, GENUINE_WITH_IMAGES)

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
    joined = " ".join(page.extract_text() for page in reader.pages)
    # The body is justified, so sentences wrap in whatever place this render
    # happened to choose. Collapse whitespace rather than writing every
    # assertion around a particular line break.
    return re.sub(r"\s+", " ", joined)


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
    # Shaped like the laboratory's references, with its own prefix so a report
    # is not mistaken for a case the laboratory opened.
    assert case_id.startswith("GLYQD/")
    assert report.financial_year(now) in case_id
    assert report_id.startswith("R-")
    # Not the predecessor's scheme (a bare millisecond timestamp).
    assert not case_id.rsplit("/", 1)[-1].isdigit()


def test_financial_year_rolls_in_april():
    from datetime import datetime, timezone

    def fy(y, m):
        return report.financial_year(datetime(y, m, 1, tzinfo=timezone.utc))

    assert fy(2026, 10) == "26-27"
    assert fy(2027, 3) == "26-27"    # March is still the old year
    assert fy(2027, 4) == "27-28"    # April starts the new one


def test_rendered_text_has_no_pass_fail_verdict_words():
    for payload in ALL_CASES:
        found = VERDICT_WORDS.findall(_text(payload))
        assert not found, f"verdict words in rendered report: {found}"


def test_rendered_text_labels_the_advisory_section():
    text = _text(GENUINE)
    assert "advisory – not used in the result" in text
    assert "5. Result of the comparison" in text
    assert "did not" in text and "contribute to the distance" in text


def test_rendered_text_keeps_the_two_summary_numbers_apart():
    """A reader must not be able to mistake the advisory mean for a confidence."""
    text = _text(GENUINE)
    assert "not combined with the margin in section 5" in text
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


# --- the letterhead format --------------------------------------------------

def test_report_never_claims_a_human_examiner():
    """The layout follows a real laboratory's signed opinion. The content must
    not: nobody examined these documents, and the document has to say so."""
    text = _text(GENUINE)
    assert "not an expert opinion" in text
    assert "No examiner has reviewed this report" in text
    assert "no signature because no one has certified its contents" in text

    lowered = text.lower()
    # No examiner name, credentials, or first-person opinion anywhere.
    for forbidden in ("debarya", "scientific officer", "i am of the opinion",
                      "in my opinion", "msc", "b.sc", "examiner:"):
        assert forbidden not in lowered, f"report implies a human examiner: {forbidden}"


def test_report_does_not_head_a_section_opinion():
    """The laboratory's report carries an 'Opinion'; a machine's carries a
    recommendation. The distinction is the whole point."""
    text = _text(GENUINE)
    assert "Recommendation" in text
    # "Opinion" appears only inside the disclaimer sentences, never as a
    # section heading of its own.
    assert not any(line.strip() == "Opinion" for line in text.splitlines())


def test_observations_section_shows_what_the_model_saw():
    text = _text(GENUINE_WITH_IMAGES)
    assert "4. Observations" in text
    assert "R1" in text and "Q1" in text
    assert "did not see the original photographs" in text


def test_images_are_actually_embedded():
    """The Observations grid is the point of the section; a silently empty one
    would still render and still read as though the images were reviewed."""
    import io

    import pypdf

    def image_count(payload):
        reader = pypdf.PdfReader(io.BytesIO(report.build_pdf(payload)))
        return sum(len(list(page.images)) for page in reader.pages)

    # A 155x155 bilevel PNG compresses to almost nothing beside the
    # letterhead, so counting bytes proves little. Count the XObjects.
    assert image_count(GENUINE_WITH_IMAGES) == image_count(GENUINE) + 2


def test_missing_images_are_declared_not_silently_dropped():
    text = _text(GENUINE)
    assert "preprocessed images were not included" in text


def test_a_corrupt_image_does_not_lose_the_report():
    payload = {**GENUINE, "preprocessed_ref_base64": "not base64 at all!!",
               "preprocessed_test_base64": "also not base64"}
    assert report.build_pdf(payload).startswith(b"%PDF")


def test_renders_without_any_letterhead_assets(monkeypatch):
    """A clone of the public repo has no letterhead. It must still produce a
    report, on the plain layout."""
    from app import letterhead

    monkeypatch.setattr(letterhead, "assets", lambda: {})
    pdf = report.build_pdf(GENUINE)
    assert pdf.startswith(b"%PDF")
    import io

    import pypdf

    text = " ".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
    assert "5. Result of the comparison" in text
    assert "not an expert opinion" in text
