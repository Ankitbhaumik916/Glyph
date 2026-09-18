"""Errors that map to a clean JSON response instead of a stack trace."""
from __future__ import annotations


class VerificationError(Exception):
    """Base for expected, user-fixable failures.

    `field` names the upload at fault ("reference" / "test") when applicable so
    the UI can point at the right dropzone.
    """

    status_code = 400
    code = "verification_error"

    def __init__(self, message: str, *, field: str | None = None, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field
        self.hint = hint


class ImageDecodeError(VerificationError):
    status_code = 415
    code = "image_decode_failed"


class ImageTooLargeError(VerificationError):
    status_code = 413
    code = "image_too_large"


class NoSignatureDetectedError(VerificationError):
    status_code = 422
    code = "no_signature_detected"


class PreprocessingFailedError(VerificationError):
    status_code = 422
    code = "preprocessing_failed"


class ModelNotLoadedError(VerificationError):
    status_code = 503
    code = "model_not_loaded"
