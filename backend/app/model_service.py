"""Loads the signature model + preprocessing pipeline and runs verification.

The architecture and preprocessing code live in the model directory (see
config.MODEL_DIR) and are imported from there rather than duplicated, so this
service always runs the exact same pipeline the model was trained against.
"""
from __future__ import annotations

import base64
import importlib.util
import io
import logging
import sys
import threading
from types import ModuleType
from typing import Any

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from . import config
from .cropping import (
    CANONICAL_MARGIN,
    CropBox,
    apply_crop,
    find_ink_box,
    render_at_margin,
)
from .errors import (
    ImageDecodeError,
    ImageTooLargeError,
    ModelNotLoadedError,
    NoSignatureDetectedError,
    PreprocessingFailedError,
)

log = logging.getLogger(__name__)

# Pillow refuses absurdly large images; we set our own ceiling explicitly.
Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS

# The bundle may store weights under any of these keys depending on how it was
# saved. Checked in order.
_STATE_KEYS = ("model_state", "state_dict", "model_state_dict", "weights")


def _import_from_model_dir(module_name: str) -> ModuleType:
    """Import `module_name`.py out of MODEL_DIR."""
    path = config.MODEL_DIR / f"{module_name}.py"
    if not path.is_file():
        raise FileNotFoundError(f"Expected {path} (set MODEL_DIR to override).")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec so intra-module imports resolve.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def decode_upload(data: bytes, field: str) -> np.ndarray:
    """Bytes -> BGR uint8 array, honouring EXIF orientation.

    Returns 3-channel BGR even for greyscale input. That matters: the
    preprocessor only runs document/signature localization when the array has
    3 dimensions, so decoding to greyscale would silently skip cropping for
    full-page photos.
    """
    if not data:
        raise ImageDecodeError(f"The {field} image is empty.", field=field)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ImageTooLargeError(
            f"The {field} image is {len(data) / 1e6:.1f} MB; the limit is "
            f"{config.MAX_UPLOAD_BYTES / 1e6:.0f} MB.",
            field=field,
            hint="Resize or re-export the photo and try again.",
        )
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)  # phone photos are often rotated
            rgb = im.convert("RGB")
            arr = np.asarray(rgb, dtype=np.uint8)
    except UnidentifiedImageError as exc:
        raise ImageDecodeError(
            f"The {field} file is not a readable image.",
            field=field,
            hint="Upload a PNG, JPEG, BMP, WEBP or TIFF file.",
        ) from exc
    except Image.DecompressionBombError as exc:
        raise ImageTooLargeError(
            f"The {field} image has too many pixels to process safely.", field=field
        ) from exc
    except OSError as exc:  # truncated / corrupt file
        raise ImageDecodeError(
            f"The {field} image could not be decoded - the file may be corrupt.",
            field=field,
        ) from exc

    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ImageDecodeError(
            f"Unexpected image format for the {field} image.", field=field
        )
    if min(arr.shape[:2]) < 16:
        raise ImageDecodeError(
            f"The {field} image is only {arr.shape[1]}x{arr.shape[0]} pixels - "
            "too small to analyse.",
            field=field,
        )
    return np.ascontiguousarray(arr[:, :, ::-1])  # RGB -> BGR


def encode_png_base64(arr01: np.ndarray) -> str:
    """Encode a float32 [0,1] HxW array as base64 PNG (no data: URI prefix)."""
    img = Image.fromarray((np.clip(arr01, 0.0, 1.0) * 255.0).astype(np.uint8), mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


class SignatureVerifier:
    """Holds the loaded model; one instance per process."""

    def __init__(self) -> None:
        self._net: Any = None
        self._preprocessor_cls: Any = None
        self._lock = threading.Lock()  # serializes the torch forward pass
        self.metadata: dict[str, Any] = {}
        self.threshold: float = 0.0
        self.bundle_threshold: float = 0.0
        self.threshold_source: str = "bundle"
        self.img_size: int = 0
        self.embed_dim: int = 0
        self.load_error: str | None = None

    @property
    def is_ready(self) -> bool:
        return self._net is not None

    def load(self) -> None:
        import torch  # imported lazily so config errors surface before torch's cost

        torch.set_num_threads(max(1, config.TORCH_NUM_THREADS))
        # Binarized, mostly-black inputs push activations into subnormal floats,
        # which the CPU handles ~20x slower. Flushing them to zero left the
        # embeddings bit-identical on CEDAR and cut inference from ~0.8s to
        # ~0.04s per image.
        torch.set_flush_denormal(True)

        if not config.BUNDLE_PATH.is_file():
            raise FileNotFoundError(
                f"Model bundle not found at {config.BUNDLE_PATH}. "
                "Set MODEL_BUNDLE or MODEL_DIR to point at it."
            )

        arch = _import_from_model_dir("model_architecture")
        preproc = _import_from_model_dir("preprocessing")
        self._preprocessor_cls = preproc.SignaturePreprocessor

        bundle = torch.load(config.BUNDLE_PATH, map_location="cpu", weights_only=False)
        if not isinstance(bundle, dict):
            raise TypeError(
                f"Expected the bundle to be a dict, got {type(bundle).__name__}."
            )

        state = next((bundle[k] for k in _STATE_KEYS if k in bundle), None)
        if state is None:
            raise KeyError(
                f"No weights found in the bundle; looked for {_STATE_KEYS}, "
                f"found keys {sorted(bundle)}."
            )
        # Tolerate checkpoints saved from DataParallel.
        state = {k.removeprefix("module."): v for k, v in state.items()}

        self.embed_dim = int(bundle.get("embed_dim", getattr(arch, "EMBED_DIM", 128)))
        self.img_size = int(bundle.get("img_size", getattr(arch, "IMG_SIZE", 155)))
        if "threshold" not in bundle:
            raise KeyError("The bundle has no 'threshold' entry.")
        self.bundle_threshold = float(bundle["threshold"])
        if config.THRESHOLD_OVERRIDE is not None:
            self.threshold = float(config.THRESHOLD_OVERRIDE)
            self.threshold_source = "calibrated"
            log.info(
                "Using calibrated threshold %.4f (bundle value %.4f)",
                self.threshold,
                self.bundle_threshold,
            )
        else:
            self.threshold = self.bundle_threshold
            self.threshold_source = "bundle"

        net = arch.SiameseSignatureNet(embed_dim=self.embed_dim)
        net.load_state_dict(state, strict=True)
        net.eval()  # critical: BatchNorm must use running stats, not batch stats
        for p in net.parameters():
            p.requires_grad_(False)
        self._net = net

        self.metadata = {
            "architecture": bundle.get("architecture"),
            "notes": bundle.get("notes"),
            "val_eer": bundle.get("val_eer"),
            "val_acc": bundle.get("val_acc"),
            "test_english_eer": bundle.get("test_english_eer"),
            "test_mixed_eer": bundle.get("test_mixed_eer"),
        }
        log.info(
            "Model loaded: %s | embed_dim=%d img_size=%d threshold=%.4f",
            self.metadata.get("architecture"),
            self.embed_dim,
            self.img_size,
            self.threshold,
        )

    @staticmethod
    def tta_margins() -> list[float]:
        """Crop margins to average over, centred on the canonical margin."""
        k = max(1, config.TTA_VARIANTS)
        if k == 1:
            return [CANONICAL_MARGIN]
        step = config.TTA_MARGIN_STEP
        start = CANONICAL_MARGIN - step * (k - 1) / 2
        return [max(0.0, round(start + i * step, 4)) for i in range(k)]

    def _process(self, bgr: np.ndarray, field: str, already_cropped: bool) -> np.ndarray:
        """One pass of the training-time pipeline. HxW float32 in [0,1]."""
        # Built per call: the preprocessor holds a cv2 CLAHE object which is not
        # documented as thread-safe, and construction is cheap.
        preprocessor = self._preprocessor_cls(out_size=self.img_size)
        try:
            out = preprocessor.process(bgr, already_cropped=already_cropped)
        except Exception as exc:  # noqa: BLE001 - surfaced as a clean 422
            log.exception("Preprocessing failed for the %s image", field)
            raise PreprocessingFailedError(
                f"Could not process the {field} image ({type(exc).__name__}).",
                field=field,
                hint="Try a sharper, better-lit photo with the signature clearly visible.",
            ) from exc

        out = np.asarray(out, dtype=np.float32)
        if out.shape != (self.img_size, self.img_size):
            raise PreprocessingFailedError(
                f"Preprocessing returned shape {out.shape}, expected "
                f"({self.img_size}, {self.img_size}).",
                field=field,
            )
        if not np.isfinite(out).all():
            raise PreprocessingFailedError(
                f"Preprocessing produced invalid pixel values for the {field} image.",
                field=field,
            )
        return out

    def run_pipeline(
        self, bgr: np.ndarray, field: str, crop: CropBox | None
    ) -> tuple[np.ndarray, float, list[np.ndarray]]:
        """Preprocess one upload.

        Returns (image to display, ink fraction, variants to embed).

        With a user crop, the automatic document/signature localization is
        skipped (it is what gets fooled by cloth, fingers and shadows), the crop
        is re-tightened to the ink so its size and shape don't leak into the
        result, and it is rendered at several margins. Those variants are
        averaged in embedding space, which damps the pipeline's sensitivity to
        the exact crop. Without a crop, the full-photo localization path runs as
        before and there is only one variant.
        """
        if crop is None:
            out = self._process(bgr, field, already_cropped=False)
            return out, float((out > 0).mean()), [out]

        cropped = apply_crop(bgr, crop, field)
        box = find_ink_box(cropped)
        if box is None:
            # No ink found; let the pipeline run so the ink check reports it.
            out = self._process(cropped, field, already_cropped=True)
            return out, float((out > 0).mean()), [out]

        margins = self.tta_margins()
        variants = [
            self._process(render_at_margin(cropped, box, m), field, already_cropped=True)
            for m in margins
        ]
        # Display the variant at the canonical margin - what the user's box maps to.
        primary = variants[min(range(len(margins)), key=lambda i: abs(margins[i] - CANONICAL_MARGIN))]
        return primary, float((primary > 0).mean()), variants

    def preprocess(
        self, bgr: np.ndarray, field: str, crop: CropBox | None
    ) -> tuple[np.ndarray, list[np.ndarray]]:
        """run_pipeline, but reject outputs with no signature in them."""
        out, ink, variants = self.run_pipeline(bgr, field, crop)
        if ink < config.MIN_INK_FRACTION:
            raise NoSignatureDetectedError(
                f"No signature strokes were found in the {field} image.",
                field=field,
                hint=(
                    "Crop closer to the signature, or use a photo with stronger "
                    "contrast between the ink and the paper."
                ),
            )
        return out, variants

    def embed_pair(
        self, ref: list[np.ndarray], test: list[np.ndarray]
    ) -> tuple[float, float]:
        """Embed every variant of both images in one forward pass.

        Returns (distance between the mean embeddings, spread of the per-variant
        distances). The spread says how much this particular pair moves when the
        crop moves - a large value means the verdict is not reproducible.

        Batching is safe only because the net is in eval mode, where BatchNorm
        uses running statistics and each sample is independent of the batch.
        """
        import torch

        if self._net is None:
            raise ModelNotLoadedError("The model is not loaded.")

        batch = torch.from_numpy(np.stack(ref + test)[:, None, :, :])  # (N,1,H,W)
        with self._lock, torch.inference_mode():
            # Per-THREAD CPU flag, so setting it at startup does not cover the
            # worker threads FastAPI runs sync endpoints on. Without it here,
            # subnormal activations make the forward pass ~20x slower.
            torch.set_flush_denormal(True)
            emb = self._net.embed(batch)
        e_ref, e_test = emb[: len(ref)], emb[len(ref) :]

        # Mean direction of the variants, renormalized back onto the unit sphere.
        m_ref = torch.nn.functional.normalize(e_ref.mean(0, keepdim=True), dim=1)
        m_test = torch.nn.functional.normalize(e_test.mean(0, keepdim=True), dim=1)
        distance = float(torch.nn.functional.pairwise_distance(m_ref, m_test, p=2).item())

        pairs = min(len(ref), len(test))
        if pairs > 1:
            per_variant = torch.nn.functional.pairwise_distance(
                e_ref[:pairs], e_test[:pairs], p=2
            )
            spread = float((per_variant.max() - per_variant.min()).item())
        else:
            spread = 0.0
        return distance, spread

    def confidence(self, distance: float) -> float:
        """How far the distance sits from the threshold, scaled to [0,1].

        This is a *margin*, not a calibrated probability: 0 means "right on the
        decision boundary", 1 means "as far into this verdict as the metric can
        go". The genuine side is scaled by the threshold itself, the forged side
        by the remaining range up to the largest possible distance between two
        L2-normalized embeddings (2.0).
        """
        if distance <= self.threshold:
            span = self.threshold if self.threshold > 0 else 1.0
            return float(np.clip((self.threshold - distance) / span, 0.0, 1.0))
        span = config.MAX_DISTANCE - self.threshold
        if span <= 0:
            return 1.0
        return float(np.clip((distance - self.threshold) / span, 0.0, 1.0))

    def _require_ready(self) -> None:
        if not self.is_ready:
            raise ModelNotLoadedError(
                "The model failed to load on startup; check the server logs.",
                hint=self.load_error,
            )

    def preview(self, data: bytes, field: str, crop: CropBox | None) -> dict[str, Any]:
        """What the model would see for one image, without running the model.

        Returns the image even when no signature is found, so the user can see
        why and adjust the crop.
        """
        self._require_ready()
        out, ink, _ = self.run_pipeline(decode_upload(data, field), field, crop)
        return {
            "preprocessed_base64": encode_png_base64(out),
            "ink_fraction": round(ink, 5),
            "signature_detected": ink >= config.MIN_INK_FRACTION,
        }

    def verify(
        self,
        ref_bytes: bytes,
        test_bytes: bytes,
        ref_crop: CropBox | None = None,
        test_crop: CropBox | None = None,
    ) -> dict[str, Any]:
        self._require_ready()

        ref_img = decode_upload(ref_bytes, "reference")
        test_img = decode_upload(test_bytes, "test")

        ref_pre, ref_variants = self.preprocess(ref_img, "reference", ref_crop)
        test_pre, test_variants = self.preprocess(test_img, "test", test_crop)

        distance, spread = self.embed_pair(ref_variants, test_variants)
        is_genuine = distance <= self.threshold

        # The verdict is assembled here, complete, from the neural distance
        # alone. Nothing below this point may alter it - the supporting
        # analysis is attached afterwards as an extra key and is not read by
        # anything that decides anything.
        verdict = {
            "distance": round(distance, 6),
            "threshold": round(self.threshold, 6),
            "max_distance": config.MAX_DISTANCE,
            "is_genuine": bool(is_genuine),
            # Within this band of the threshold the verdict is not reproducible
            # across re-drawn crops, so the UI reports it as too close to call.
            "is_borderline": bool(abs(distance - self.threshold) < config.BORDERLINE_BAND),
            "borderline_band": round(config.BORDERLINE_BAND, 4),
            "variants": min(len(ref_variants), len(test_variants)),
            "variant_spread": round(spread, 6),
            "confidence": round(self.confidence(distance), 4),
            "preprocessed_ref_base64": encode_png_base64(ref_pre),
            "preprocessed_test_base64": encode_png_base64(test_pre),
        }

        verdict["forensic"] = self._supporting_analysis(
            ref_img, test_img, ref_crop, test_crop
        )
        return verdict

    def _supporting_analysis(
        self,
        ref_img: np.ndarray,
        test_img: np.ndarray,
        ref_crop: CropBox | None,
        test_crop: CropBox | None,
    ) -> dict[str, Any] | None:
        """Classical-CV similarity scores, for display only.

        Returns None - and the UI omits the section - when either image has no
        user-drawn box. Without one the analysis would be measuring paper,
        shadows and fingers rather than handwriting, and confident-looking
        numbers computed from noise are worse than no numbers.

        Failures are swallowed on purpose: this is an explanatory extra, and a
        bug in it must never take down a verification.
        """
        if not config.FORENSIC_ENABLED or ref_crop is None or test_crop is None:
            return None
        try:
            from . import forensic_features

            return forensic_features.compare(
                apply_crop(ref_img, ref_crop, "reference"),
                apply_crop(test_img, test_crop, "test"),
            )
        except Exception:  # noqa: BLE001 - never let this break a verdict
            log.exception("supporting visual analysis failed; continuing without it")
            return None


verifier = SignatureVerifier()
