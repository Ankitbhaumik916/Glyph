"""Reviews, stored in a private Hugging Face dataset repo.

The Space's own disk is wiped on restart, so reviews go to a dataset repo on
the owner's account instead. That repo is private, which is what actually keeps
reviews owner-only - the admin key below just gates the convenience endpoint.

One file per review rather than one appended file: two testers submitting at the
same moment would otherwise overwrite each other.
"""
from __future__ import annotations

import hmac
import json
import logging
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from . import config
from .errors import VerificationError

log = logging.getLogger(__name__)


class ReviewsUnavailableError(VerificationError):
    status_code = 503
    code = "reviews_unavailable"


class NotAuthorizedError(VerificationError):
    status_code = 401
    code = "not_authorized"


class ReviewsTokenRejectedError(VerificationError):
    """The server's own HF token was refused - not the caller's admin key.

    These are trivial to confuse: the admin key gates the endpoint, the HF
    token is what the server then uses to reach the dataset. A rotated token
    used to surface here as a generic 500, which reads on the admin page as if
    the key that was just typed were wrong. It is a separate code so the page
    can say which credential actually failed.
    """

    status_code = 503
    code = "reviews_token_rejected"


@contextmanager
def _translate_hf_errors():
    """Turn a 401/403 from Hugging Face into a message naming the real cause."""
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - re-raised unless it is an auth failure
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (401, 403):
            raise ReviewsTokenRejectedError(
                "Hugging Face rejected this server's access token, so reviews cannot "
                "be read or saved. Your admin key is fine - the server's token was "
                "most likely revoked or rotated.",
                hint=(
                    "Set HF_TOKEN on the Space to a current write token for the "
                    "account that owns the dataset, then restart the Space."
                ),
            ) from exc
        raise


class ReviewStore:
    def __init__(self) -> None:
        self._api: Any = None
        self._lock = threading.Lock()
        self._repo_checked = False

    @property
    def enabled(self) -> bool:
        return bool(config.HF_TOKEN and config.REVIEWS_DATASET)

    @property
    def admin_enabled(self) -> bool:
        return bool(config.ADMIN_KEY)

    def _client(self):
        """HfApi, created on first use so the import cost is only paid if used."""
        if self._api is None:
            try:
                from huggingface_hub import HfApi
            except ImportError as exc:  # pragma: no cover - dependency is pinned
                raise ReviewsUnavailableError(
                    "The server is missing huggingface_hub, so reviews cannot be saved."
                ) from exc
            self._api = HfApi(token=config.HF_TOKEN)
        return self._api

    def _ensure_repo(self) -> None:
        """Create the dataset repo once per process if it isn't there yet."""
        if self._repo_checked:
            return
        with self._lock:
            if self._repo_checked:
                return
            with _translate_hf_errors():
                self._client().create_repo(
                    repo_id=config.REVIEWS_DATASET,
                    repo_type="dataset",
                    private=True,
                    exist_ok=True,
                )
            self._repo_checked = True

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise ReviewsUnavailableError(
                "Reviews are not configured on this server.",
                hint="Set HF_TOKEN and REVIEWS_DATASET on the Space.",
            )

    def submit(self, review: dict[str, Any]) -> str:
        self._require_enabled()
        self._ensure_repo()

        now = datetime.now(timezone.utc)
        review_id = f"{now.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
        record = {"id": review_id, "submitted_at": now.isoformat(), **review}

        with _translate_hf_errors():
            self._client().upload_file(
                path_or_fileobj=json.dumps(record, indent=2).encode("utf-8"),
                path_in_repo=f"reviews/{review_id}.json",
                repo_id=config.REVIEWS_DATASET,
                repo_type="dataset",
                commit_message=f"review {review_id}",
            )
        log.info("review %s saved to %s", review_id, config.REVIEWS_DATASET)
        return review_id

    def authorize(self, key: str | None) -> None:
        if not self.admin_enabled:
            raise NotAuthorizedError(
                "Review reading is disabled because no admin key is set on the server."
            )
        # compare_digest to avoid leaking the key through response timing.
        if not key or not hmac.compare_digest(key, config.ADMIN_KEY):
            raise NotAuthorizedError("Wrong admin key.")

    def list(self, limit: int = 200) -> list[dict[str, Any]]:
        """Newest first. Low volume, so each review is fetched individually."""
        self._require_enabled()
        self._ensure_repo()
        api = self._client()

        with _translate_hf_errors():
            files = [
                f for f in api.list_repo_files(config.REVIEWS_DATASET, repo_type="dataset")
                if f.startswith("reviews/") and f.endswith(".json")
            ]
        files.sort(reverse=True)  # ids start with a timestamp

        from huggingface_hub import hf_hub_download

        out: list[dict[str, Any]] = []
        for name in files[:limit]:
            try:
                with _translate_hf_errors():
                    path = hf_hub_download(
                        repo_id=config.REVIEWS_DATASET,
                        filename=name,
                        repo_type="dataset",
                        token=config.HF_TOKEN,
                    )
                with open(path, encoding="utf-8") as fh:
                    out.append(json.load(fh))
            except ReviewsTokenRejectedError:
                raise  # a dead token fails every file; report it, don't return []
            except Exception:  # noqa: BLE001 - one bad file shouldn't hide the rest
                log.exception("Could not read review %s", name)
        return out


store = ReviewStore()
