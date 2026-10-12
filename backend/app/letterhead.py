"""Letterhead assets for the exported report.

WHY THESE ARE NOT IN THE REPOSITORY
    The GitHub repo and the Hugging Face Space are both public. The header band
    carries the lab's accreditation marks, QR code and office addresses, so
    committing it would publish a ready-made kit for producing documents on an
    accredited forensic laboratory's letterhead. The files live in the private
    dataset repo instead and are fetched once per process.

    Everything here is optional. With no assets available the report renders on
    a plain Glyph letterhead, so a clone of the public repo is fully working -
    it just does not carry someone else's branding.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

# Published names in the dataset, under a letterhead/ prefix.
ASSETS = ("header.jpg", "footer.png", "qr.png", "watermark.png")

_lock = threading.Lock()
_resolved: dict[str, Path] | None = None


def _local_dir() -> Path:
    if config.LETTERHEAD_DIR:
        return Path(config.LETTERHEAD_DIR)
    return Path(__file__).resolve().parent / "assets" / "letterhead"


def _dataset() -> str:
    return config.LETTERHEAD_DATASET or config.REVIEWS_DATASET


def _fetch_into(directory: Path) -> None:
    """Pull any missing assets out of the private dataset."""
    if not (config.HF_TOKEN and _dataset()):
        return
    from huggingface_hub import hf_hub_download

    directory.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        target = directory / name
        if target.exists():
            continue
        try:
            cached = hf_hub_download(
                repo_id=_dataset(),
                filename=f"letterhead/{name}",
                repo_type="dataset",
                token=config.HF_TOKEN,
            )
            target.write_bytes(Path(cached).read_bytes())
        except Exception:  # noqa: BLE001 - a missing letterhead is not an error
            log.info("letterhead asset %s not available; continuing without it", name)


def assets() -> dict[str, Path]:
    """Available assets by name. Empty dict means render the plain letterhead.

    Resolved once per process: the files do not change between requests, and a
    report render should not wait on the Hub.
    """
    global _resolved
    if _resolved is not None:
        return _resolved
    with _lock:
        if _resolved is not None:
            return _resolved
        directory = _local_dir()
        if not all((directory / name).exists() for name in ASSETS):
            _fetch_into(directory)
        found = {name: directory / name for name in ASSETS if (directory / name).exists()}
        if found:
            log.info("letterhead: %d/%d assets loaded from %s",
                     len(found), len(ASSETS), directory)
        else:
            log.info("letterhead: no assets found; reports use the plain layout")
        _resolved = found
        return _resolved


def reset_cache() -> None:
    """For tests."""
    global _resolved
    _resolved = None
