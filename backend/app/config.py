"""Runtime configuration, all overridable by environment variable."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent

# Directory holding model_architecture.py, preprocessing.py and the .pt bundle.
MODEL_DIR = Path(os.getenv("MODEL_DIR", str(PROJECT_ROOT / "model"))).resolve()
BUNDLE_PATH = Path(
    os.getenv("MODEL_BUNDLE", str(MODEL_DIR / "signature_model_bundle.pt"))
).resolve()

# Reject oversized uploads before decoding them.
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))

# Largest side we allow a decoded image to have. Guards against decompression
# bombs; the preprocessor downsamples to 350px anyway.
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", str(50_000_000)))

# Fraction of the 155x155 output that must be ink for us to believe a signature
# was actually found. A blank page preprocesses to an (almost) empty canvas.
MIN_INK_FRACTION = float(os.getenv("MIN_INK_FRACTION", "0.004"))

# Embeddings are L2-normalized, so Euclidean distance is bounded by 2.0.
# Used to scale the "how far past the threshold" confidence signal.
MAX_DISTANCE = 2.0

# Number of crop margins averaged per image when a user crop is supplied.
# The pipeline's Hough deskew picks noticeably different angles for tiny changes
# in its input, so a single crop makes the distance jumpy; averaging embeddings
# over several fixed margins around the ink stabilizes it. Measured on 55 CEDAR
# genuine pairs, each re-cropped by hand 5 times: the verdict flipped between
# runs for 9/55 pairs with 1 variant, 3/55 with 5, 1/55 with 7. Set 1 to disable.
TTA_VARIANTS = int(os.getenv("TTA_VARIANTS", "7"))
# Margins are centred on cropping.CANONICAL_MARGIN with this spacing.
TTA_MARGIN_STEP = float(os.getenv("TTA_MARGIN_STEP", "0.03"))

# Distances this close to the threshold are reported as "too close to call":
# the residual crop sensitivity is about as large as the gap to the boundary, so
# the verdict is not reproducible there. Of the 8/55 genuine pairs sitting
# within 0.05 of the threshold, 5 flipped between hand-redrawn crops.
BORDERLINE_BAND = float(os.getenv("BORDERLINE_BAND", "0.05"))

# Decision threshold measured on your own photos, replacing the bundle's, which
# was chosen on scanned research datasets. Produce one with tools/calibrate.py.
_threshold_override = os.getenv("THRESHOLD_OVERRIDE", "").strip()
THRESHOLD_OVERRIDE: float | None = float(_threshold_override) if _threshold_override else None

CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if o.strip()
]

# Vercel gives every deployment its own hostname, so preview builds can't be
# listed one by one. Set e.g. https://glyph-.*\.vercel\.app to allow them.
CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX", "").strip() or None

# --- Reviews -----------------------------------------------------------------
# Testers leave a review after each comparison. They are written to a PRIVATE
# Hugging Face dataset repo, because the Space's own disk does not survive a
# restart. Both of these must be set for the feature to switch on.
HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
REVIEWS_DATASET = os.getenv("REVIEWS_DATASET", "").strip()  # e.g. AnkBhau/glyph-reviews

# Gates the endpoint that reads reviews back. The dataset being private is the
# real protection; this keeps the convenience endpoint from being world-readable.
ADMIN_KEY = os.getenv("ADMIN_KEY", "").strip()

# Inference is small; leaving torch to grab every core hurts more than it helps.
TORCH_NUM_THREADS = int(os.getenv("TORCH_NUM_THREADS", "4"))
