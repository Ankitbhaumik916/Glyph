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


def financial_year(now: datetime) -> str:
    """Indian financial year as the lab writes it: "26-27" for Oct 2026."""
    start = now.year if now.month >= 4 else now.year - 1
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


def new_ids(now: datetime) -> tuple[str, str]:
    """Fresh case and report identifiers, per export.

    Shaped like the lab's own case references (GLYQD/26-27/xxxx) so a report
    files alongside them, but with its own GLYQD prefix: these are produced by
    software, and must not be mistaken for a case the laboratory opened.
    """
    return (
        f"GLYQD/{financial_year(now)}/{uuid.uuid4().hex[:4].upper()}",
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


# --- page furniture ---------------------------------------------------------
# Geometry in millimetres, matched to the laboratory's own reports: letterhead
# band and QR at the top of every page, the sub-brand line beneath it, the
# contact bar and page number at the foot.
_PAGE_W, _PAGE_H = 210.0, 297.0
_MARGIN = 18.0
_CONTENT_W = _PAGE_W - 2 * _MARGIN
_BAND_W = 150.0
_FOOTER_W = 160.0


def _draw_furniture(canvas, doc, assets: dict) -> None:
    """Header, watermark, contact bar and page number, on every page."""
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    canvas.saveState()

    # Watermark first, so everything else sits on top of it.
    if "watermark.png" in assets:
        size = 120.0
        canvas.drawImage(
            str(assets["watermark.png"]),
            (_PAGE_W - size) / 2 * mm, (_PAGE_H - size) / 2 * mm,
            width=size * mm, height=size * mm,
            mask="auto", preserveAspectRatio=True,
        )

    if "header.jpg" in assets:
        band_h = _BAND_W * 148.0 / 1078.0          # the asset's own aspect
        top = _PAGE_H - 8.0
        canvas.drawImage(
            str(assets["header.jpg"]),
            _MARGIN * mm, (top - band_h) * mm,
            width=_BAND_W * mm, height=band_h * mm,
            mask="auto", preserveAspectRatio=True,
        )
        if "qr.png" in assets:
            qr = 15.0
            canvas.drawImage(
                str(assets["qr.png"]),
                (_MARGIN + _BAND_W + 6.0) * mm, (top - band_h / 2 - qr / 2) * mm,
                width=qr * mm, height=qr * mm,
                mask="auto", preserveAspectRatio=True,
            )
        canvas.setFont("Times-Bold", 9.5)
        canvas.setFillColor(colors.black)
        canvas.drawCentredString(_PAGE_W / 2 * mm, (top - band_h - 4.0) * mm,
                                 "A unit of Forensibus")
    else:
        # Plain fallback, so a clone without the private assets still renders.
        canvas.setFont("Helvetica-Bold", 16)
        canvas.setFillColor(colors.HexColor(NAVY))
        canvas.drawString(_MARGIN * mm, (_PAGE_H - 20.0) * mm, "GLYPH")
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawRightString((_PAGE_W - _MARGIN) * mm, (_PAGE_H - 20.0) * mm,
                               "SIGNATURE VERIFICATION REPORT")
        canvas.setStrokeColor(colors.HexColor(NAVY))
        canvas.setLineWidth(1.2)
        canvas.line(_MARGIN * mm, (_PAGE_H - 23.0) * mm,
                    (_PAGE_W - _MARGIN) * mm, (_PAGE_H - 23.0) * mm)

    if "footer.png" in assets:
        bar_h = _FOOTER_W * 24.0 / 1187.0
        canvas.drawImage(
            str(assets["footer.png"]),
            (_MARGIN + (_CONTENT_W - _FOOTER_W) / 2) * mm, 12.0 * mm,
            width=_FOOTER_W * mm, height=bar_h * mm,
            mask="auto", preserveAspectRatio=True,
        )
    canvas.setFont("Times-Bold", 10)
    canvas.setFillColor(colors.black)
    canvas.drawRightString((_PAGE_W - _MARGIN) * mm, 12.0 * mm, str(canvas.getPageNumber()))

    canvas.restoreState()


def _signature_image(base64_png: str, side_mm: float):
    """A preprocessed 155x155 signature as a flowable, or None."""
    import base64 as b64
    from io import BytesIO

    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage

    if not base64_png:
        return None
    try:
        raw = b64.b64decode(base64_png, validate=True)
    except Exception:  # noqa: BLE001 - a malformed preview must not lose the report
        log.warning("could not decode a preprocessed image for the report")
        return None
    return RLImage(BytesIO(raw), width=side_mm * mm, height=side_mm * mm)


def build_pdf(d: dict[str, Any]) -> bytes:
    """Render the report. `d` is a verify result plus display metadata."""
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    from . import letterhead

    now = datetime.now(timezone.utc)
    case_id, report_id = new_ids(now)
    forensic = d.get("forensic")
    assets = letterhead.assets()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=34 * mm,       # clears the letterhead band
        bottomMargin=20 * mm,    # clears the contact bar
        leftMargin=_MARGIN * mm,
        rightMargin=_MARGIN * mm,
        title=f"Glyph Signature Verification Report {case_id}",
        author="Glyph",
    )

    styles = getSampleStyleSheet()
    # Times throughout, as the laboratory's reports are set.
    body = ParagraphStyle("Body", parent=styles["Normal"], fontName="Times-Roman",
                          fontSize=11, leading=16, alignment=4)  # justified
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Times-Bold",
                        fontSize=13, textColor=colors.black,
                        spaceBefore=12, spaceAfter=6)
    centre_h = ParagraphStyle("CentreH", parent=h2, alignment=1, spaceBefore=14)
    caseline = ParagraphStyle("Case", parent=body, fontName="Times-Italic", fontSize=11)
    small = ParagraphStyle("Small", parent=body, fontSize=9, leading=12.5)
    cap = ParagraphStyle("Cap", parent=body, fontName="Times-Roman", fontSize=10,
                         alignment=1, spaceBefore=2)
    # The laboratory's reports bullet with a dingbat arrow, but neither U+25B8
    # nor the ZapfDingbats arrow survives the standard-font encoding here -
    # both come out as a filled box. A plain bullet is in WinAnsi and renders.
    bullet = ParagraphStyle("Bullet", parent=body, leftIndent=18, bulletIndent=6,
                            spaceAfter=4, bulletFontSize=10)
    numbered = ParagraphStyle("Numbered", parent=body, leftIndent=20, bulletIndent=4,
                              spaceAfter=6)

    story: list[Any] = []

    # --- case reference line ------------------------------------------------
    story.append(Table(
        [[Paragraph(f"Case Reference No: {case_id}", caseline),
          Paragraph(f"Date: {now.strftime('%d/%m/%Y')}", caseline)]],
        colWidths=[_CONTENT_W * 0.6 * mm, _CONTENT_W * 0.4 * mm],
        style=TableStyle([
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]),
    ))

    # --- 1. Reference -------------------------------------------------------
    story.append(Paragraph("1. Reference", h2))
    story.append(Paragraph("The following images have been submitted for comparison.", body))
    story.append(Spacer(1, 4))
    cropped = d.get("variants", 1) > 1
    story.append(Paragraph(
        "<b>Reference signature</b> &ndash; the specimen supplied as known-genuine, "
        "marked as R1.", bullet, bulletText="•"))
    story.append(Paragraph(
        "<b>Questioned signature</b> &ndash; the signature to be compared against it, "
        "marked as Q1.", bullet, bulletText="•"))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        ("Both were supplied as photographs. A crop box was drawn on each, and the "
         f"comparison was averaged over {d.get('variants')} crop margins."
         if cropped else
         "Both were supplied as photographs. No crop box was drawn, so the signature "
         "region was located automatically and the comparison was not averaged over "
         "crop margins."), body))

    # --- 2. Basis of the comparison ----------------------------------------
    story.append(Paragraph("2. Basis of the comparison", h2))
    story.append(Paragraph(
        "Each signature is reduced by a convolutional neural network to a "
        "128-dimensional embedding, and the two embeddings are compared by Euclidean "
        "distance. The network was trained on signature pairs so that a smaller distance "
        "corresponds to a greater likelihood of common authorship. A fixed decision "
        "threshold, established on held-out data, separates the same-writer range from "
        "the different-writer range.", body))
    story.append(Paragraph(
        "This is a learned similarity measure over the image as a whole. It is not a "
        "characteristic-by-characteristic examination of movement, line quality, "
        "proportion or letter formation, and it does not reason about the natural "
        "variation of a writer's hand. The supporting measurements in section 6 are "
        "reported alongside it for description only.", body))

    # --- 3. About this examination -----------------------------------------
    # Where the laboratory's report introduces the examiner. There is no
    # examiner here, and the document says so rather than leaving a gap that
    # reads as though one was involved.
    story.append(Paragraph("3. About this examination", h2))
    story.append(Paragraph(
        "This comparison was performed by an automated system. <b>No forensic document "
        "examiner has examined these documents, and this report is not an expert "
        "opinion.</b> Nothing in it has been reviewed by a person, and it carries no "
        "signature because no one has certified its contents.", body))
    story.append(Paragraph(
        "On held-out data the system was measured at an equal-error rate of 0.17 to "
        "0.23. Roughly one comparison in five can therefore be wrong, in either "
        "direction. It is intended as a triage aid that indicates which comparisons "
        "merit examination, not as a determination of authorship.", body))

    # --- 4. Observations ----------------------------------------------------
    story.append(Paragraph("4. Observations", h2))
    story.append(Paragraph(
        "The images below are the output of the preprocessing pipeline &ndash; document "
        "localization, CLAHE, Sauvola binarization, deskew and stroke normalization "
        "&ndash; at 155&times;155 pixels. This is the whole of what the network "
        "received: it did not see the original photographs. Where these are cropped to "
        "the wrong region, are missing strokes, or carry heavy speckle, the comparison "
        "below is not meaningful and should be disregarded.", body))
    story.append(Spacer(1, 6))

    ref_img = _signature_image(d.get("preprocessed_ref_base64", ""), 42)
    test_img = _signature_image(d.get("preprocessed_test_base64", ""), 42)
    if ref_img and test_img:
        grid = Table(
            [[ref_img, test_img],
             [Paragraph("R1 &ndash; Reference", cap),
              Paragraph("Q1 &ndash; Questioned", cap)]],
            colWidths=[_CONTENT_W / 2 * mm] * 2,
        )
        grid.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.75, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.75, colors.black),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
        ]))
        story.append(KeepTogether(grid))
    else:
        story.append(Paragraph(
            "<i>The preprocessed images were not included with this export.</i>", body))

    # --- 5. Result ----------------------------------------------------------
    label, colour = _verdict_label(bool(d["is_genuine"]), bool(d["is_borderline"]))
    story.append(Paragraph("5. Result of the comparison", h2))

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
    story.append(Paragraph(
        "Operating point: " + " &middot; ".join(status_bits),
        ParagraphStyle("Status", parent=small, fontName="Courier", fontSize=8)))
    story.append(Spacer(1, 5))

    verdict_box = Table(
        [[Paragraph(
            f"<b>{label}</b><br/>Margin from threshold: "
            f"{float(d['confidence']) * 100:.1f}%",
            ParagraphStyle("V", parent=body, fontName="Times-Bold", fontSize=13,
                           textColor=colors.white, leading=19, alignment=0))]],
        colWidths=[_CONTENT_W * mm],
    )
    verdict_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(colour)),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(verdict_box)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Produced by the verification model alone. The margin is the distance from the "
        "decision boundary, not a probability.", small))
    story.append(Spacer(1, 5))
    story.append(Paragraph(_model_narrative(d), body))
    story.append(Spacer(1, 7))

    spread_cell = f"{d.get('variant_spread', 0.0):.3f}" if d.get("variants", 1) > 1 else "n/a"
    metrics = Table(
        [["Distance", "Threshold", "Margin", "Crop sensitivity"],
         [f"{d['distance']:.4f}", f"{d['threshold']:.4f}",
          f"{float(d['confidence']) * 100:.1f}%", spread_cell]],
        colWidths=[_CONTENT_W / 4 * mm] * 4,
    )
    metrics.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PANEL)),
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Courier-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(metrics)

    # --- 6. Supporting visual analysis -------------------------------------
    story.append(Paragraph(
        "6. Supporting visual analysis (advisory &ndash; not used in the result)", h2))
    story.append(Paragraph(
        "Classical image measurements comparing the two signatures, computed "
        "independently of the network. They did not contribute to the distance, the "
        "threshold or the result in section 5, and no score here is combined with the "
        "margin reported there. Each was retained only where a change of writer moves "
        "it further than lighting, resolution and photographic angle do. There is no "
        "pass mark: the scores are uncalibrated, so a row may be compared between pairs "
        "but not against any absolute bar.", body))
    story.append(Spacer(1, 5))

    if forensic:
        scores: dict[str, float | None] = forensic.get("scores") or {}
        rows: list[list[Any]] = [["Feature", "Score", "Status", "What it compares"]]
        for key in (k for k in FEATURE_LABELS if k in scores):
            value = scores[key]
            rows.append([
                Paragraph(FEATURE_LABELS[key],
                          ParagraphStyle("FL", parent=small, fontSize=9)),
                f"{value:.2f}" if value is not None else "-",
                "Measured" if value is not None else "Not measurable",
                Paragraph(FEATURE_NOTES.get(key, ""),
                          ParagraphStyle("FN", parent=small, fontSize=8, leading=10.5)),
            ])
        feat_tbl = Table(rows, colWidths=[32 * mm, 13 * mm, 23 * mm, 106 * mm],
                         repeatRows=1)
        feat_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PANEL)),
            ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTNAME", (1, 1), (2, -1), "Times-Roman"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 1), (2, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(feat_tbl)

        mean = forensic.get("mean_score")
        measured_n, total_n = forensic.get("measured"), forensic.get("total")
        if mean is not None:
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                f"Mean of the {measured_n} measurable rows: {float(mean) * 100:.0f}%. An "
                f"average of this section only &ndash; it is not a confidence, and it is "
                f"not combined with the margin in section 5.", small))
        if isinstance(total_n, int) and isinstance(measured_n, int) and measured_n < total_n:
            story.append(Paragraph(
                f"{total_n - measured_n} of {total_n} rows could not be measured for "
                f"this pair.", small))
        story.append(Paragraph(
            f"Previously reported and since withdrawn: {', '.join(RETIRED_FEATURES)}. "
            f"Both were measured against capture noise and did not survive it, so they "
            f"are no longer computed.", small))
    else:
        story.append(Paragraph(
            "No supporting measurements were taken for this comparison. These are "
            "computed only when a crop box was drawn on both images.", body))

    # --- 7. Advisory observations ------------------------------------------
    story.append(Paragraph("7. Advisory observations", h2))
    story.append(Paragraph(
        "Notes on section 6. None of these affected the result, and none should be read "
        "as one.", small))
    story.append(Spacer(1, 4))
    for i, flag in enumerate(_advisory_flags(forensic), start=1):
        story.append(Paragraph(flag, numbered, bulletText=f"{i}."))

    # --- Recommendation, where the laboratory's report carries the Opinion --
    story.append(Paragraph("Recommendation", centre_h))
    story.append(Paragraph(_recommendation(d), body))
    story.append(Spacer(1, 14))

    # No signature block: nobody signed this.
    sign_off = Table(
        [[Paragraph(f"<b>Date:</b> {now.strftime('%d/%m/%Y')}", body),
          Paragraph(
              "<b>Generated by Glyph</b><br/>"
              "<font size=9>Automated signature comparison<br/>"
              "No examiner has reviewed this report</font>",
              ParagraphStyle("Sign", parent=body, alignment=1))]],
        colWidths=[_CONTENT_W * 0.45 * mm, _CONTENT_W * 0.55 * mm],
    )
    sign_off.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(sign_off)

    # --- Note ---------------------------------------------------------------
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<b>Note</b>: {DISCLAIMER}", small))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"Report ID: {report_id} &nbsp;|&nbsp; Case Reference No: {case_id}", small))

    def furniture(canvas, doc_):
        _draw_furniture(canvas, doc_, assets)

    doc.build(story, onFirstPage=furniture, onLaterPages=furniture)
    return buffer.getvalue()
