"""FastAPI service for Siamese signature verification.

Run from the `backend/` directory:
    uvicorn app.main:app --port 8000 --reload
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, Header, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .cropping import parse_crop
from .errors import VerificationError
from .model_service import verifier
from .reviews import store as review_store
from .schemas import (
    ErrorResponse,
    HealthResponse,
    PreviewResponse,
    ReviewAck,
    ReviewIn,
    ReviewList,
    VerifyResponse,
)

CROP_FIELD_DESCRIPTION = (
    'Optional JSON crop box in 0-1 units of the EXIF-oriented image, e.g. '
    '{"x":0.1,"y":0.3,"width":0.7,"height":0.25}. When given, automatic '
    "document/signature localization is skipped."
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
)
log = logging.getLogger("signature-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the model once at startup.

    A load failure does not kill the process: the service stays up and reports
    the reason through /api/health, which is far easier to debug than a
    container that exits immediately.
    """
    try:
        verifier.load()
    except Exception as exc:  # noqa: BLE001
        verifier.load_error = f"{type(exc).__name__}: {exc}"
        log.error("MODEL FAILED TO LOAD - /api/verify will return 503. %s", verifier.load_error)
    yield


app = FastAPI(
    title="Glyph API",
    description=(
        "Siamese-network signature verification. Research prototype - use as a "
        "decision-support signal alongside expert review, not a sole determinant."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=config.CORS_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(VerificationError)
async def verification_error_handler(request: Request, exc: VerificationError):
    """Expected failures -> structured JSON the UI can render."""
    log.info("%s on %s: %s", exc.code, request.url.path, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "field": exc.field,
                "hint": exc.hint,
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    """Anything unexpected: log the traceback, return a clean message."""
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Something went wrong while processing the request.",
                "field": None,
                "hint": "Check the backend server logs for details.",
            }
        },
    )


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """Liveness + model readiness. The frontend polls this to warn when the
    backend is down before the user bothers uploading anything."""
    if not verifier.is_ready:
        return HealthResponse(
            status="degraded", model_loaded=False, error=verifier.load_error
        )
    return HealthResponse(
        status="ok",
        model_loaded=True,
        threshold=round(verifier.threshold, 6),
        bundle_threshold=round(verifier.bundle_threshold, 6),
        threshold_source=verifier.threshold_source,
        borderline_band=round(config.BORDERLINE_BAND, 4),
        reviews_enabled=review_store.enabled,
        img_size=verifier.img_size,
        embed_dim=verifier.embed_dim,
        model_info=verifier.metadata,
    )


@app.post(
    "/api/verify",
    response_model=VerifyResponse,
    responses={
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    tags=["verification"],
)
def verify(
    reference: UploadFile = File(..., description="Known-genuine reference signature."),
    test: UploadFile = File(..., description="Signature to check against the reference."),
    reference_crop: str | None = Form(None, description=CROP_FIELD_DESCRIPTION),
    test_crop: str | None = Form(None, description=CROP_FIELD_DESCRIPTION),
) -> VerifyResponse:
    """Preprocess both uploads, embed them, and compare against the threshold.

    Defined with `def` rather than `async def` on purpose: FastAPI runs sync
    endpoints in a worker thread, which keeps the CPU-bound OpenCV and torch
    work off the event loop.
    """
    started = time.perf_counter()
    ref_bytes = reference.file.read()
    test_bytes = test.file.read()

    ref_box = parse_crop(reference_crop, "reference")
    test_box = parse_crop(test_crop, "test")

    result = verifier.verify(ref_bytes, test_bytes, ref_box, test_box)

    log.info(
        "verify: distance=%.4f threshold=%.4f genuine=%s borderline=%s "
        "variants=%d spread=%.4f cropped=%s/%s in %.0f ms",
        result["distance"],
        result["threshold"],
        result["is_genuine"],
        result["is_borderline"],
        result["variants"],
        result["variant_spread"],
        ref_box is not None,
        test_box is not None,
        (time.perf_counter() - started) * 1000,
    )
    return VerifyResponse(**result)


@app.post(
    "/api/preprocess",
    response_model=PreviewResponse,
    responses={413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    tags=["verification"],
)
def preprocess_preview(
    image: UploadFile = File(..., description="A single signature image."),
    field: str = Form("reference", description='"reference" or "test"; only used in error messages.'),
    crop: str | None = Form(None, description=CROP_FIELD_DESCRIPTION),
) -> PreviewResponse:
    """Run preprocessing only, so the UI can show the model's input while the
    user adjusts the crop - before spending a verification on it."""
    label = field if field in ("reference", "test") else "uploaded"
    return PreviewResponse(**verifier.preview(image.file.read(), label, parse_crop(crop, label)))


@app.post(
    "/api/reviews",
    response_model=ReviewAck,
    responses={503: {"model": ErrorResponse}},
    tags=["reviews"],
)
def submit_review(review: ReviewIn) -> ReviewAck:
    """Save a tester's feedback on one comparison.

    Anyone who can use the app can leave a review; only the owner can read them
    back, because they land in a private dataset repo.
    """
    review_id = review_store.submit(review.model_dump())
    return ReviewAck(id=review_id)


@app.get(
    "/api/reviews",
    response_model=ReviewList,
    responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    tags=["reviews"],
)
def list_reviews(x_admin_key: str | None = Header(None)) -> ReviewList:
    """Read the reviews back. Requires the admin key in an X-Admin-Key header."""
    review_store.authorize(x_admin_key)
    reviews = review_store.list()
    return ReviewList(reviews=reviews, count=len(reviews))
