"""Exportable PDF report for a single comparison.

WHAT THIS IS
    A pure rendering function: comparison numbers in, PDF bytes out. It is
    called from its own endpoint, never from verify(), and it computes no
    scores of its own.

THE ONE RULE THIS FILE EXISTS TO KEEP
    The predecessor project's report merged the neural similarity and an
    aggregate of the forensic features into a single "SWGDOC verdict" with one
    confidence number. That is the bug this codebase was rebuilt to remove: the
    forensic measurements are weak and partly confounded, so folding them into
    the verdict corrupted verdicts that the model had got right.

    So this report has two sections that never meet:
      - MODEL VERDICT, built only from the model's own output (distance,
        threshold, genuine/borderline, margin);
      - FORENSIC FEATURE ANALYSIS, explicitly labelled advisory and not used in
        the verdict.
    There is deliberately no number anywhere that combines them, and no flag
    derived from the advisory section is allowed to read as a verdict.
    tests/test_report.py fails if a combined score or a PASS/FAIL verdict word
    appears in the rendered text.

NO PASS/FAIL PER FEATURE
    forensic_features.py is explicit that its constants set the scale of a
    score and not its meaning, and that thresholds must not be derived from
    them. So the Status column reports whether a feature could be measured at
    all - never whether it passed. A per-feature pass mark would be the old
    merged verdict again, one level down.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

# Carried over from the predecessor report so the two look like the same family
# of document. Visual only - none of its scoring came with it.
NAVY = "#1a2b4a"
PANEL = "#f0f3f8"
RULE = "#cdd6e6"
GREEN = "#1f8a44"
RED = "#c0392b"
AMBER = "#d68910"
MUTED = "#5a6b8a"

# Display names, matching the on-screen panel so a reader moving between the
# two sees the same words.
FEATURE_LABELS: dict[str, str] = {
    "line_quality": "Line quality",
    "stroke_direction": "Stroke direction",
    "size_proportion": "Size & proportion",
    "alignment_slant": "Alignment & slant",
    "proportion_spacing": "Proportion & spacing",
}

# What each measurement actually compares, plus how much of it survives a
# change of camera. The ratios are the measured writer-signal-to-capture-noise
# figures recorded in forensic_features.py and the README; they are stated here
# so a reader can weigh a row instead of treating all five as equally solid.
FEATURE_NOTES: dict[str, str] = {
    "line_quality": (
        "Smoothness and curvature of the strokes. The least camera-robust of the "
        "kept measurements (a change of writer moves it only about 1.5x as much "
        "as lighting, focus and JPEG artifacts do), so small differences in this "
        "row carry little weight."
    ),
    "stroke_direction": (
        "Distribution of stroke directions, measured relative to each "
        "signature's own baseline. Robust to capture conditions (about 25x)."
    ),
    "size_proportion": (
        "Width-to-height ratio and ink density, with density taken from skeleton "
        "length so that defocus thickening strokes does not register as a "
        "difference. Robust to capture conditions (about 14x)."
    ),
    "alignment_slant": (
        "Dominant stroke slant and baseline alignment, measured relative to the "
        "signature's own baseline rather than the page, so the angle the paper "
        "sat at does not contribute. Robust to capture conditions (about 22x)."
    ),
    "proportion_spacing": (
        "Relative widths of stroke groups and the gaps between them. The most "
        "camera-robust of the five (about 400x), being a ratio of ratios."
    ),
}

# Retired after measurement; named so a reader comparing against an older
# report does not think the rows were silently dropped.
RETIRED_FEATURES = ("Letter formation", "Terminal strokes")


def new_ids(now: datetime) -> tuple[str, str]:
    """Fresh case and report identifiers. Not the predecessor's scheme."""
    stamp = now.strftime("%Y%m%d")
    return (
        f"GLY-{stamp}-{uuid.uuid4().hex[:6].upper()}",
        f"R-{uuid.uuid4().hex[:12].upper()}",
    )


def _verdict_label(is_genuine: bool, is_borderline: bool) -> tuple[str, str]:
    """The on-screen wording and its colour. Mirrors ResultPanel exactly."""
    if is_borderline:
        return "TOO CLOSE TO CALL", AMBER
    if is_genuine:
        return "LIKELY AUTHENTIC", GREEN
    return "LIKELY FORGED", RED


def _model_narrative(d: dict[str, Any]) -> str:
    """Prose for the verdict box, from model output only."""
    distance = d["distance"]
    threshold = d["threshold"]
    band = d.get("borderline_band", 0.05)
    variants = d.get("variants", 1)
    spread = d.get("variant_spread", 0.0)

    if d["is_borderline"]:
        side = "just inside" if d["is_genuine"] else "just outside"
        text = (
            f"The embedding distance between the two signatures is {distance:.4f}, "
            f"within {band:.2f} of the {threshold:.4f} decision threshold "
            f"({side}). At this range the result is not reproducible - re-drawing "
            f"the crop boxes can flip it - so it is reported as inconclusive "
            f"rather than as a finding."
        )
    elif d["is_genuine"]:
        text = (
            f"The embedding distance between the two signatures is {distance:.4f}, "
            f"below the {threshold:.4f} decision threshold, so the model places "
            f"this pair in the same-writer range."
        )
    else:
        text = (
            f"The embedding distance between the two signatures is {distance:.4f}, "
            f"above the {threshold:.4f} decision threshold, so the model places "
            f"this pair in the different-writer range."
        )

    if variants > 1:
        text += (
            f" The comparison was averaged over {variants} crop margins; the "
            f"distance varied by {spread:.3f} across them"
            + (
                ", which is high - this pair is sensitive to exactly where the "
                "boxes were drawn."
                if spread > 0.2
                else "."
            )
        )
    else:
        text += (
            " No crop boxes were drawn, so the comparison was not averaged over "
            "crop margins and is more sensitive to framing than it needs to be."
        )
    return text


def _advisory_flags(forensic: dict[str, Any] | None) -> list[str]:
    """Observations from the advisory section only.

    Nothing here may read as a verdict: no severity, no pass/fail, no
    recommendation to disbelieve the model. Factual notes a reader needs in
    order to not over-read the table.
    """
    if not forensic:
        return [
            "No advisory measurements were taken for this comparison, because a "
            "crop box was not drawn on both images. Without one these "
            "measurements would describe paper, shadows and fingers rather than "
            "the signatures."
        ]

    scores: dict[str, float | None] = forensic.get("scores") or {}
    flags: list[str] = []

    unmeasured = [FEATURE_LABELS.get(k, k) for k, v in scores.items() if v is None]
    if unmeasured:
        flags.append(
            f"Not measurable for this pair: {', '.join(unmeasured)}. Reported as "
            f"unmeasured rather than as a low score, because a feature that "
            f"cannot be computed is not evidence of a difference."
        )

    measured = {k: v for k, v in scores.items() if v is not None}
    if measured:
        low_key = min(measured, key=lambda k: measured[k])
        high_key = max(measured, key=lambda k: measured[k])
        flags.append(
            f"Across the measurable rows the lowest similarity was "
            f"{FEATURE_LABELS.get(low_key, low_key)} at {measured[low_key]:.2f} "
            f"and the highest was {FEATURE_LABELS.get(high_key, high_key)} at "
            f"{measured[high_key]:.2f}."
        )

    if measured.get("line_quality") is not None:
        flags.append(
            "Line quality is the least camera-robust of the five measurements; "
            "a difference in that row alone is as likely to be the photograph "
            "as the writer."
        )

    flags.append(
        "These measurements separate writers only weakly even at their best. "
        "They are included to describe what the two signatures have in common, "
        "not to support a conclusion."
    )
    return flags


def _recommendation(d: dict[str, Any]) -> str:
    """Follows from the model verdict alone - never from the advisory section."""
    if d["is_borderline"]:
        action = (
            "Treat this comparison as inconclusive and do not act on it. Obtain a "
            "further known-genuine reference signature and repeat the comparison, "
            "or refer the pair to a qualified document examiner."
        )
    elif d["is_genuine"]:
        action = (
            "The comparison is consistent with the two signatures having been "
            "written by the same person. For anything consequential, confirm "
            "against a second known-genuine reference before relying on it."
        )
    else:
        action = (
            "The comparison is not consistent with the two signatures having been "
            "written by the same person. Refer the pair to a qualified document "
            "examiner before acting; do not treat this output as a finding of "
            "forgery."
        )
    return (
        f"{action} This recommendation follows from the model verdict above and "
        f"from nothing else - the advisory measurements in the preceding section "
        f"were not an input to it."
    )


DISCLAIMER = (
    "This report is machine-generated output from an automated signature "
    "comparison and is not the opinion of a qualified forensic document "
    "examiner. It has no evidentiary standing. The underlying model was measured "
    "at an equal-error rate of 0.17-0.23 on held-out data, meaning roughly one "
    "comparison in five can be wrong in either direction; it is a triage aid, "
    "not a determination. The decision threshold is a fixed operating point, not "
    "a calibrated probability, and the reported margin is the distance from that "
    "boundary rather than a likelihood. The forensic feature section is "
    "descriptive and was not used to produce the verdict; its scores are "
    "uncalibrated and must not be compared against any absolute bar. No "
    "conclusion in this document should be relied upon as the sole basis for a "
    "decision affecting any person."
)


def build_pdf(d: dict[str, Any]) -> bytes:
    """Render the report. `d` is a verify result plus display metadata."""
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    now = datetime.now(timezone.utc)
    case_id, report_id = new_ids(now)
    forensic = d.get("forensic")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=f"Glyph Signature Verification Report {case_id}",
        author="Glyph",
    )

    styles = getSampleStyleSheet()
    brand = ParagraphStyle("Brand", parent=styles["Title"], fontSize=20,
                           alignment=0, textColor=colors.HexColor(NAVY), spaceAfter=2)
    subtitle = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=10,
                              textColor=colors.HexColor(MUTED))
    mono = ParagraphStyle("Mono", parent=styles["Normal"], fontSize=8,
                          fontName="Courier", textColor=colors.HexColor(MUTED))
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12,
                        textColor=colors.HexColor(NAVY), spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9.5, leading=13)
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=7.5,
                           textColor=colors.HexColor("#666666"), leading=10)

    story: list[Any] = []

    # --- header ------------------------------------------------------------
    header = Table(
        [[Paragraph("GLYPH", brand),
          Paragraph("SIGNATURE VERIFICATION REPORT", subtitle)]],
        colWidths=[60 * mm, 110 * mm],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(header)
    story.append(Paragraph("Siamese CNN comparison with supporting visual analysis", subtitle))
    story.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor(NAVY)))
    story.append(Spacer(1, 6))

    # --- case bar ----------------------------------------------------------
    case_tbl = Table([[
        Paragraph(f"<b>Case ID:</b> {case_id}", body),
        Paragraph(f"<b>Date:</b> {now.strftime('%Y-%m-%d %H:%M:%S')} UTC", body),
        Paragraph(f"<b>Doc Type:</b> {d.get('document_type') or 'Signature comparison'}", body),
    ]], colWidths=[57 * mm, 60 * mm, 53 * mm])
    case_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(PANEL)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(RULE)),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(RULE)),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(case_tbl)

    # The result page's status bar, verbatim, so a report can be tied back to
    # the operating point that produced it.
    source = (d.get("threshold_source") or "bundle").strip().lower()
    status_bits = [
        "model ready",
        f"threshold {d['threshold']:.4f}",
        "CALIBRATED" if source == "calibrated" else "BUNDLE DEFAULT",
    ]
    if source == "calibrated" and d.get("bundle_threshold") is not None:
        status_bits.append(f"bundle default was {d['bundle_threshold']:.4f}")
    if d.get("model_architecture"):
        status_bits.append(str(d["model_architecture"]))
    story.append(Spacer(1, 3))
    story.append(Paragraph(" &middot; ".join(status_bits), mono))

    # --- model verdict -----------------------------------------------------
    label, colour = _verdict_label(bool(d["is_genuine"]), bool(d["is_borderline"]))
    story.append(Paragraph("MODEL VERDICT", h2))
    verdict_text = (
        f"<b>{label}</b><br/>Margin from threshold: "
        f"{float(d['confidence']) * 100:.1f}%"
    )
    verdict_box = Table(
        [[Paragraph(verdict_text, ParagraphStyle(
            "V", parent=body, fontSize=12, textColor=colors.white, leading=18))]],
        colWidths=[170 * mm],
    )
    verdict_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(colour)),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(verdict_box)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Produced by the verification model alone. The margin is the distance "
        "from the decision boundary, not a probability.", small))
    story.append(Spacer(1, 4))
    story.append(Paragraph(_model_narrative(d), body))
    story.append(Spacer(1, 5))

    spread_cell = f"{d.get('variant_spread', 0.0):.3f}" if d.get("variants", 1) > 1 else "n/a"
    metrics = Table(
        [
            ["Distance", "Threshold", "Margin", "Crop sensitivity"],
            [
                f"{d['distance']:.4f}",
                f"{d['threshold']:.4f}",
                f"{float(d['confidence']) * 100:.1f}%",
                spread_cell,
            ],
        ],
        colWidths=[42.5 * mm] * 4,
    )
    metrics.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PANEL)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(NAVY)),
        ("FONTNAME", (0, 1), (-1, 1), "Courier-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(RULE)),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(metrics)

    # --- advisory section --------------------------------------------------
    story.append(Paragraph(
        "FORENSIC FEATURE ANALYSIS (ADVISORY - NOT USED IN VERDICT)", h2))
    story.append(Paragraph(
        "Classical image measurements comparing the two signatures, computed "
        "independently of the model. They did not contribute to the distance, "
        "the threshold or the verdict above, and no score in this section is "
        "combined with the margin reported above. Each was kept only where a "
        "change of writer moves it further than lighting, resolution and photo "
        "angle do. There is no pass mark: these scores are uncalibrated, so a "
        "row is comparable between pairs but not against any absolute bar.",
        body))
    story.append(Spacer(1, 4))

    if forensic:
        scores: dict[str, float | None] = forensic.get("scores") or {}
        rows: list[list[Any]] = [["Feature", "Score", "Status", "What it compares"]]
        # Driven by the response, so a feature retired on the backend simply
        # stops appearing instead of printing as a gap.
        for key in (k for k in FEATURE_LABELS if k in scores):
            value = scores[key]
            rows.append([
                FEATURE_LABELS[key],
                f"{value:.2f}" if value is not None else "-",
                "Measured" if value is not None else "Not measurable",
                Paragraph(FEATURE_NOTES.get(key, ""),
                          ParagraphStyle("FN", parent=body, fontSize=7.5, leading=9.5)),
            ])
        feat_tbl = Table(rows, colWidths=[34 * mm, 14 * mm, 22 * mm, 100 * mm], repeatRows=1)
        feat_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(RULE)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 1), (2, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(feat_tbl)

        mean = forensic.get("mean_score")
        measured_n = forensic.get("measured")
        total_n = forensic.get("total")
        if mean is not None:
            story.append(Spacer(1, 3))
            story.append(Paragraph(
                f"Mean of the {measured_n} measurable rows: {float(mean) * 100:.0f}%. "
                f"An average of this section only - it is not a confidence, and it "
                f"is not combined with the model margin above.", small))
        if isinstance(total_n, int) and isinstance(measured_n, int) and measured_n < total_n:
            story.append(Paragraph(
                f"{total_n - measured_n} of {total_n} rows could not be measured "
                f"for this pair.", small))
        story.append(Spacer(1, 2))
        story.append(Paragraph(
            f"Previously reported and since withdrawn: "
            f"{', '.join(RETIRED_FEATURES)}. Both were measured against capture "
            f"noise and did not survive it, so they are no longer computed.", small))
    else:
        story.append(Paragraph(
            "No advisory measurements were taken for this comparison. These are "
            "only computed when a crop box was drawn on both images.", body))

    # --- flags -------------------------------------------------------------
    story.append(Paragraph("ADVISORY OBSERVATIONS", h2))
    story.append(Paragraph(
        "Notes on the advisory section above. None of these affected the "
        "verdict, and none should be read as one.", small))
    story.append(Spacer(1, 3))
    for flag in _advisory_flags(forensic):
        story.append(Paragraph(f"&bull; {flag}", body))
        story.append(Spacer(1, 2))

    # --- recommendation ----------------------------------------------------
    story.append(Paragraph("RECOMMENDATION", h2))
    story.append(Paragraph(_recommendation(d), body))

    # --- disclaimer --------------------------------------------------------
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor(RULE)))
    story.append(Paragraph("DISCLAIMER", ParagraphStyle(
        "DiscH", parent=small, fontSize=8, textColor=colors.HexColor("#444444"))))
    story.append(Paragraph(DISCLAIMER, small))
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        f"Report ID: {report_id} &nbsp;|&nbsp; Case ID: {case_id} "
        f"&nbsp;|&nbsp; Generated by Glyph, no human examiner involved", small))

    doc.build(story)
    return buffer.getvalue()
