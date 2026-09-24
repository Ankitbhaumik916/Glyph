"""Response models. These define the contract the Next.js frontend codes against."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class VerifyResponse(BaseModel):
    distance: float = Field(
        ..., description="Euclidean distance between the two L2-normalized embeddings."
    )
    threshold: float = Field(..., description="Decision threshold stored in the bundle.")
    max_distance: float = Field(
        2.0,
        description=(
            "Largest distance two L2-normalized embeddings can have. Useful for "
            "drawing the score on a fixed scale."
        ),
    )
    is_genuine: bool = Field(..., description="True when distance <= threshold.")
    is_borderline: bool = Field(
        False,
        description=(
            "True when the distance is within borderline_band of the threshold. The "
            "verdict is then not reproducible across re-drawn crops - treat it as "
            "inconclusive rather than as a decision."
        ),
    )
    borderline_band: float = Field(0.05, description="Half-width of the inconclusive band.")
    variants: int = Field(
        1, description="Crop margins averaged per image (1 when no crop was supplied)."
    )
    variant_spread: float = Field(
        0.0,
        description=(
            "Max minus min distance across the per-variant comparisons. Larger means "
            "this pair is more sensitive to exactly where the crop falls."
        ),
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Margin from the decision boundary, scaled to [0,1]. Not a calibrated "
            "probability."
        ),
    )
    preprocessed_ref_base64: str = Field(
        ..., description="Base64 PNG of the reference image as the model saw it (no data: prefix)."
    )
    preprocessed_test_base64: str = Field(
        ..., description="Base64 PNG of the test image as the model saw it (no data: prefix)."
    )
    forensic: ForensicAnalysis | None = Field(
        None,
        description=(
            "Supporting visual analysis, shown beside the verdict and never used "
            "in it. None when no crop box was drawn, or when the feature is off."
        ),
    )


class PreviewResponse(BaseModel):
    preprocessed_base64: str = Field(
        ..., description="Base64 PNG of the image as the model would see it (no data: prefix)."
    )
    ink_fraction: float = Field(..., description="Fraction of the output that is ink.")
    signature_detected: bool = Field(
        ..., description="False when /api/verify would reject this image as having no signature."
    )


class ReviewIn(BaseModel):
    """A tester's feedback on one comparison."""

    rating: int = Field(..., ge=1, le=5, description="1-5 stars.")
    verdict_correct: Literal["yes", "no", "unsure"] | None = Field(
        None, description="Did the app's verdict match what the tester knew to be true?"
    )
    comment: str = Field("", max_length=2000)
    name: str = Field("", max_length=120, description="Optional, so you can follow up.")
    # Context copied from the result, so a review is readable on its own.
    distance: float | None = None
    threshold: float | None = None
    is_genuine: bool | None = None
    is_borderline: bool | None = None
    variant_spread: float | None = None


class ReviewAck(BaseModel):
    id: str
    status: str = "saved"


class ReviewRecord(ReviewIn):
    id: str
    submitted_at: str


class ReviewList(BaseModel):
    reviews: list[ReviewRecord]
    count: int


class ForensicAnalysis(BaseModel):
    """Supporting visual analysis. Explanatory only - see forensic_features.py.

    Nothing in here is an input to distance, is_genuine, is_borderline or
    confidence. A score of None means the feature was not measurable for this
    pair, which is reported as such rather than as a low score.
    """

    scores: dict[str, float | None]
    mean_score: float | None = Field(
        None,
        description=(
            "Mean of the measurable scores, for display only. Deliberately NOT "
            "fused with the neural confidence."
        ),
    )
    measured: int
    total: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None
    hint: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    # `model_loaded` / `model_info` collide with pydantic's protected `model_`
    # namespace; we keep the field names and disable the guard.
    model_config = ConfigDict(protected_namespaces=())

    status: str
    model_loaded: bool
    threshold: float | None = None
    bundle_threshold: float | None = None
    threshold_source: str | None = Field(
        None, description='"bundle" or "calibrated" (THRESHOLD_OVERRIDE is set).'
    )
    borderline_band: float | None = None
    img_size: int | None = None
    embed_dim: int | None = None
    model_info: dict[str, Any] | None = None
    reviews_enabled: bool = False
    error: str | None = None
