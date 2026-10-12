"""Email/password accounts, with a single hardcoded admin.

WHERE ACCOUNTS LIVE
    In a private Hugging Face dataset repo, the same place and for the same
    reason as reviews: the Space's own disk is wiped on every restart, so a
    SQLite file there would silently lose every account between deploys. One
    JSON document per user, at a path derived from a hash of the email, so a
    lookup is a single fetch rather than a listing - and so the repo's file
    names are not a list of everyone's email address.

    This is a small-scale store. Writes are git commits (slow, ~1s) and there
    is no compare-and-set, so it suits company testers, not a public userbase.

WHAT IS AND IS NOT THE SECURITY BOUNDARY
    `is_admin()` below is the only place the admin address is compared, and the
    server is the only place it is compared at all. The frontend never receives
    the admin email: login and /me return a boolean the server computed, so
    hiding the Reviews link is driven by that flag. Hiding the link is UX. The
    check inside the reviews endpoint is the boundary.

ADMIN CANNOT BE REGISTERED
    Signup refuses the admin address outright, and the admin account is created
    at startup from ADMIN_EMAIL + ADMIN_PASSWORD. Otherwise whoever signed up
    with that address first would become the admin.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from . import config
from .errors import VerificationError

log = logging.getLogger(__name__)

# scrypt parameters. n=2^15 costs ~60ms per hash here, which is the point: it
# is the only thing standing between a leaked store and the passwords in it.
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
# scrypt needs 128 * n * r bytes - about 33MB at these parameters - and
# OpenSSL refuses anything over 32MB unless the ceiling is raised explicitly.
_SCRYPT_MAXMEM = 96 * 1024 * 1024

MIN_PASSWORD_LENGTH = 10
# RFC 7518 wants an HMAC key at least as long as the hash. Anything shorter
# weakens every session token, so it is called out rather than silently used.
MIN_SECRET_LENGTH = 32
# Deliberately permissive: this validates shape, not deliverability.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


class AuthDisabledError(VerificationError):
    status_code = 503
    code = "auth_disabled"


class AccountStoreError(VerificationError):
    status_code = 503
    code = "account_store_unavailable"


class InvalidCredentialsError(VerificationError):
    status_code = 401
    code = "invalid_credentials"


class NotAuthenticatedError(VerificationError):
    status_code = 401
    code = "not_authenticated"


class ForbiddenError(VerificationError):
    status_code = 403
    code = "forbidden"


class EmailTakenError(VerificationError):
    status_code = 409
    code = "email_taken"


# --- the admin check, in one place ------------------------------------------

def normalize_email(email: str) -> str:
    return (email or "").strip().casefold()


def is_admin(email: str | None) -> bool:
    """The single definition of admin. Nothing else may compare the address.

    Exact match on the configured address, after case folding. Gmail's dot and
    +tag aliases are NOT treated as equivalent: `ankit.bhaumik23@gmail.com`
    reaches the same inbox but is a different string, and the safe direction
    for that ambiguity is to deny.
    """
    admin = normalize_email(config.ADMIN_EMAIL)
    if not admin:
        return False
    return bool(email) and hmac.compare_digest(normalize_email(email), admin)


# --- password hashing -------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N,
                            r=_SCRYPT_R, p=_SCRYPT_P, dklen=32,
                            maxmem=_SCRYPT_MAXMEM)
    return "$".join(["scrypt", str(_SCRYPT_N), str(_SCRYPT_R), str(_SCRYPT_P),
                     salt.hex(), digest.hex()])


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, want_hex = encoded.split("$")
        if scheme != "scrypt":
            return False
        got = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                             n=int(n), r=int(r), p=int(p),
                             dklen=len(bytes.fromhex(want_hex)),
                             maxmem=_SCRYPT_MAXMEM)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, bytes.fromhex(want_hex))


# --- session tokens ---------------------------------------------------------

def _require_secret() -> str:
    """No secret, no auth. There is deliberately no default.

    A baked-in fallback would mean anyone who has read this file can mint a
    token for any email, including the admin's.
    """
    if not config.AUTH_SECRET:
        raise AuthDisabledError(
            "Accounts are not configured on this server.",
            hint="Set AUTH_SECRET (and ADMIN_EMAIL/ADMIN_PASSWORD) on the Space.",
        )
    return config.AUTH_SECRET


def warn_on_weak_secret() -> None:
    """Called at startup. A weak signing key is worth a loud log line."""
    secret = config.AUTH_SECRET
    if not secret:
        log.warning("AUTH_SECRET is not set: accounts and login are switched off.")
    elif len(secret) < MIN_SECRET_LENGTH:
        log.warning(
            "AUTH_SECRET is only %d characters; use at least %d "
            "(python -c \"import secrets; print(secrets.token_urlsafe(32))\"). "
            "Short keys weaken every session token.",
            len(secret), MIN_SECRET_LENGTH,
        )


def issue_token(email: str) -> tuple[str, int]:
    """A signed session token and its lifetime in seconds."""
    import jwt

    secret = _require_secret()
    ttl = timedelta(hours=config.SESSION_TTL_HOURS)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": normalize_email(email),
            "iat": int(now.timestamp()),
            "exp": int((now + ttl).timestamp()),
        },
        secret,
        algorithm="HS256",
    )
    return token, int(ttl.total_seconds())


def email_from_token(token: str) -> str:
    """The email a token attests to, or raise.

    `is_admin` is never read from the token - it is recomputed from the email
    on every request, so a token cannot carry a stale or forged admin claim.
    """
    import jwt

    secret = _require_secret()
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise NotAuthenticatedError("Your session has expired. Sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise NotAuthenticatedError("Invalid session.") from exc
    email = normalize_email(claims.get("sub", ""))
    if not email:
        raise NotAuthenticatedError("Invalid session.")
    return email


def email_from_header(authorization: str | None) -> str:
    """Pull the session email out of an `Authorization: Bearer ...` header."""
    if not authorization:
        raise NotAuthenticatedError("Sign in to continue.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise NotAuthenticatedError("Sign in to continue.")
    return email_from_token(token.strip())


# --- the user store ---------------------------------------------------------

@contextmanager
def _hf_guard():
    """Name the real cause when the Hub refuses the server's own token."""
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - re-raised unless it is an auth failure
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (401, 403):
            raise AccountStoreError(
                "Hugging Face rejected this server's access token, so accounts "
                "cannot be read or written. This is the server's credential, "
                "not yours.",
                hint="Set HF_TOKEN on the Space to a current write token.",
            ) from exc
        raise


class UserStore:
    def __init__(self) -> None:
        self._api: Any = None
        self._lock = threading.Lock()
        self._repo_checked = False

    @property
    def dataset(self) -> str:
        return config.USERS_DATASET or config.REVIEWS_DATASET

    @property
    def enabled(self) -> bool:
        return bool(config.HF_TOKEN and self.dataset and config.AUTH_SECRET)

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise AuthDisabledError(
                "Accounts are not configured on this server.",
                hint="Set HF_TOKEN, USERS_DATASET (or REVIEWS_DATASET) and AUTH_SECRET.",
            )

    def _client(self):
        if self._api is None:
            try:
                from huggingface_hub import HfApi
            except ImportError as exc:  # pragma: no cover - dependency is pinned
                raise AccountStoreError(
                    "The server is missing huggingface_hub, so accounts cannot be stored."
                ) from exc
            self._api = HfApi(token=config.HF_TOKEN)
        return self._api

    def _ensure_repo(self) -> None:
        if self._repo_checked:
            return
        with self._lock:
            if self._repo_checked:
                return
            with _hf_guard():
                self._client().create_repo(repo_id=self.dataset, repo_type="dataset",
                                           private=True, exist_ok=True)
            self._repo_checked = True

    @staticmethod
    def _path_for(email: str) -> str:
        """A stable path per email, without putting the address in the name."""
        digest = hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()
        return f"users/{digest}.json"

    def get(self, email: str) -> dict[str, Any] | None:
        """The stored record, or None. Never cached: a password may have changed."""
        self._require_enabled()
        self._ensure_repo()
        from huggingface_hub import hf_hub_download
        from huggingface_hub.errors import EntryNotFoundError

        try:
            with _hf_guard():
                path = hf_hub_download(
                    repo_id=self.dataset,
                    filename=self._path_for(email),
                    repo_type="dataset",
                    token=config.HF_TOKEN,
                    # A login right after a signup must not read a cached miss.
                    force_download=True,
                )
        except EntryNotFoundError:
            return None
        except AccountStoreError:
            raise
        except Exception as exc:  # noqa: BLE001 - a missing file arrives as several types
            if "404" in str(exc) or "EntryNotFound" in type(exc).__name__:
                return None
            raise
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def create(self, email: str, password: str) -> dict[str, Any]:
        self._require_enabled()
        self._ensure_repo()

        email = normalize_email(email)
        record = {
            "email": email,
            "password": hash_password(password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with _hf_guard():
            self._client().upload_file(
                path_or_fileobj=json.dumps(record, indent=2).encode("utf-8"),
                path_in_repo=self._path_for(email),
                repo_id=self.dataset,
                repo_type="dataset",
                commit_message="new account",
            )
        log.info("account created (admin=%s)", is_admin(email))
        return record

    def seed_admin(self) -> None:
        """Create the admin account at startup if it is not there yet.

        Called from the app's lifespan. Signup refuses the admin address, so
        this is the only way that account can come into existence.
        """
        if not self.enabled or not config.ADMIN_EMAIL or not config.ADMIN_PASSWORD:
            return
        try:
            if self.get(config.ADMIN_EMAIL) is not None:
                return
            self.create(config.ADMIN_EMAIL, config.ADMIN_PASSWORD)
            log.info("seeded the admin account")
        except Exception:  # noqa: BLE001 - never block startup over this
            log.exception("could not seed the admin account")


store = UserStore()


# --- the operations the endpoints call --------------------------------------

def _validate(email: str, password: str) -> str:
    email = normalize_email(email)
    if not _EMAIL_RE.match(email):
        raise VerificationError("That does not look like an email address.", field="email")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise VerificationError(
            f"Use at least {MIN_PASSWORD_LENGTH} characters.", field="password"
        )
    return email


def signup(email: str, password: str) -> dict[str, Any]:
    email = _validate(email, password)
    if is_admin(email):
        # Without this, the first person to register the admin address would
        # own the Reviews page.
        raise ForbiddenError(
            "That address cannot be registered.",
            field="email",
            hint="The owner account is created on the server.",
        )
    if store.get(email) is not None:
        raise EmailTakenError("That email already has an account.", field="email")
    store.create(email, password)
    return session_for(email)


def login(email: str, password: str) -> dict[str, Any]:
    email = normalize_email(email)
    record = store.get(email)
    # Same error and roughly the same cost either way, so the response does not
    # reveal which addresses have accounts.
    if record is None:
        hash_password(password)
        raise InvalidCredentialsError("Wrong email or password.")
    if not verify_password(password, record.get("password", "")):
        raise InvalidCredentialsError("Wrong email or password.")
    return session_for(email)


def session_for(email: str) -> dict[str, Any]:
    token, expires_in = issue_token(email)
    return {
        "token": token,
        "email": normalize_email(email),
        # Computed here, sent to the client. The client never learns which
        # address is the admin one - only whether this session is it.
        "is_admin": is_admin(email),
        "expires_in": expires_in,
    }


def require_admin(authorization: str | None) -> str:
    """Authorize a request against the admin account. Returns the email."""
    email = email_from_header(authorization)
    if not is_admin(email):
        # Deliberately not 404: the caller is authenticated, just not allowed.
        raise ForbiddenError("This page is only available to the site owner.")
    return email
