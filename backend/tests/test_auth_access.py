"""Review data must be unreachable by anyone who is not the owner.

The point of these tests is the case that a UI-only guard would pass: a user
who is genuinely signed in, with a valid session, calling the API directly.
Hiding the nav link does nothing for that request, so the endpoint is what has
to refuse it.

The user store is replaced with an in-memory stand-in, so none of this touches
Hugging Face.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import auth, config

ADMIN = "ankitbhaumik23@gmail.com"
TESTER = "tester@example.com"
PASSWORD = "correct-horse-battery"
ADMIN_KEY = "the-admin-key"


class FakeStore:
    """Same surface as auth.UserStore, backed by a dict."""

    def __init__(self) -> None:
        self.records: dict[str, dict] = {}
        self.enabled = True

    def get(self, email: str):
        return self.records.get(auth.normalize_email(email))

    def create(self, email: str, password: str):
        email = auth.normalize_email(email)
        record = {"email": email, "password": auth.hash_password(password),
                  "created_at": datetime.now(timezone.utc).isoformat()}
        self.records[email] = record
        return record

    def seed_admin(self) -> None:
        if config.ADMIN_EMAIL and config.ADMIN_PASSWORD:
            self.create(config.ADMIN_EMAIL, config.ADMIN_PASSWORD)


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret-not-the-real-one-and-long-enough-for-hs256")
    monkeypatch.setattr(config, "ADMIN_EMAIL", ADMIN)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setattr(config, "SESSION_TTL_HOURS", 1)
    fake = FakeStore()
    monkeypatch.setattr(auth, "store", fake)
    fake.seed_admin()
    fake.create(TESTER, PASSWORD)
    return fake


@pytest.fixture
def client(store, monkeypatch):
    """App client with the model and the reviews backend stubbed out."""
    from fastapi.testclient import TestClient

    from app import main

    from app.reviews import NotAuthorizedError

    def fake_authorize(key: str | None) -> None:
        if key != ADMIN_KEY:
            raise NotAuthorizedError("Wrong admin key.")

    monkeypatch.setattr(main.auth, "store", store)
    monkeypatch.setattr(main.review_store, "list", lambda limit=200: [])
    monkeypatch.setattr(main.review_store, "authorize", fake_authorize)
    # The model is not needed for any of this and loading it is slow.
    monkeypatch.setattr(main.verifier, "load", lambda: None)
    with TestClient(main.app) as c:
        yield c


def _token(client, email: str, password: str = PASSWORD) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


# --- the admin check --------------------------------------------------------

def test_is_admin_matches_only_the_configured_address(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_EMAIL", ADMIN)
    assert auth.is_admin(ADMIN)
    assert auth.is_admin("  ANKITBHAUMIK23@GMAIL.COM  ")  # trimmed, case-folded
    assert not auth.is_admin(TESTER)
    assert not auth.is_admin("")
    assert not auth.is_admin(None)
    # Near misses, including the Gmail alias that reaches the same inbox: the
    # safe direction for that ambiguity is to deny.
    for near in ("ankit.bhaumik23@gmail.com", "ankitbhaumik23+x@gmail.com",
                 "ankitbhaumik23@gmail.co", "xankitbhaumik23@gmail.com",
                 "ankitbhaumik23@gmail.com.evil.test"):
        assert not auth.is_admin(near), near


def test_is_admin_denies_everyone_when_unset(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_EMAIL", "")
    assert not auth.is_admin(ADMIN)
    assert not auth.is_admin("")


# --- passwords and tokens ---------------------------------------------------

def test_password_roundtrip():
    encoded = auth.hash_password(PASSWORD)
    assert PASSWORD not in encoded          # never stored in the clear
    assert auth.verify_password(PASSWORD, encoded)
    assert not auth.verify_password("wrong-" + PASSWORD, encoded)
    assert not auth.verify_password(PASSWORD, "garbage")
    assert not auth.verify_password(PASSWORD, "")


def test_password_hash_is_salted():
    assert auth.hash_password(PASSWORD) != auth.hash_password(PASSWORD)


def test_token_roundtrip(store):
    token, ttl = auth.issue_token(TESTER)
    assert ttl > 0
    assert auth.email_from_token(token) == TESTER


def test_token_from_another_secret_is_rejected(store, monkeypatch):
    import jwt

    forged = jwt.encode({"sub": ADMIN,
                         "exp": int((datetime.now(timezone.utc)
                                     + timedelta(hours=1)).timestamp())},
                        "a-different-secret", algorithm="HS256")
    with pytest.raises(auth.NotAuthenticatedError):
        auth.email_from_token(forged)


def test_expired_token_is_rejected(store):
    import jwt

    stale = jwt.encode({"sub": ADMIN,
                        "exp": int((datetime.now(timezone.utc)
                                    - timedelta(seconds=5)).timestamp())},
                       config.AUTH_SECRET, algorithm="HS256")
    with pytest.raises(auth.NotAuthenticatedError):
        auth.email_from_token(stale)


def test_admin_is_not_read_from_the_token(store):
    """A token claiming admin for a non-admin email must not grant it.

    is_admin is recomputed from the subject on every request, so the claim is
    ignored even though the token is correctly signed.
    """
    import jwt

    token = jwt.encode(
        {"sub": TESTER, "is_admin": True, "adm": True, "role": "admin",
         "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())},
        config.AUTH_SECRET, algorithm="HS256")
    assert auth.email_from_token(token) == TESTER
    with pytest.raises(auth.ForbiddenError):
        auth.require_admin(f"Bearer {token}")


def test_auth_is_off_without_a_secret(monkeypatch):
    """No AUTH_SECRET must switch accounts off, not fall back to a default."""
    monkeypatch.setattr(config, "AUTH_SECRET", "")
    with pytest.raises(auth.AuthDisabledError):
        auth.issue_token(TESTER)
    with pytest.raises(auth.AuthDisabledError):
        auth.email_from_token("anything")


# --- signup rules -----------------------------------------------------------

def test_admin_address_cannot_be_registered(store):
    """Otherwise whoever signs up with it first owns the Reviews page."""
    with pytest.raises(auth.ForbiddenError):
        auth.signup(ADMIN, "a-brand-new-password")
    with pytest.raises(auth.ForbiddenError):
        auth.signup("  ANKITBHAUMIK23@GMAIL.COM ", "a-brand-new-password")
    # The seeded password still works, i.e. the attempt changed nothing.
    assert auth.login(ADMIN, PASSWORD)["is_admin"] is True


def test_signup_rejects_a_duplicate_email(store):
    with pytest.raises(auth.EmailTakenError):
        auth.signup(TESTER, "another-long-password")


def test_signup_validates_input(store):
    from app.errors import VerificationError

    with pytest.raises(VerificationError):
        auth.signup("not-an-email", "a-long-enough-password")
    with pytest.raises(VerificationError):
        auth.signup("new@example.com", "short")


def test_new_signup_is_not_admin(store):
    session = auth.signup("someone.else@example.com", "a-long-enough-password")
    assert session["is_admin"] is False


def test_login_does_not_reveal_whether_an_account_exists(store):
    """Same code and message for an unknown email as for a wrong password."""
    missing = pytest.raises(auth.InvalidCredentialsError)
    with missing as unknown:
        auth.login("nobody@example.com", PASSWORD)
    with pytest.raises(auth.InvalidCredentialsError) as wrong:
        auth.login(TESTER, "definitely-the-wrong-password")
    assert str(unknown.value) == str(wrong.value)


def test_session_never_carries_the_admin_address(store):
    """The browser gets a flag, not the address."""
    session = auth.login(TESTER, PASSWORD)
    assert ADMIN not in repr(session)
    assert session["is_admin"] is False


# --- the endpoint guard -----------------------------------------------------

def test_reviews_rejects_anonymous(client):
    assert client.get("/api/reviews").status_code == 401


def test_reviews_rejects_a_logged_in_non_admin(client):
    """The case a UI-only guard would let through."""
    token = _token(client, TESTER)
    response = client.get("/api/reviews", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert "reviews" not in response.text.lower() or "owner" in response.text.lower()


def test_reviews_allows_the_admin_session(client):
    token = _token(client, ADMIN)
    response = client.get("/api/reviews", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"reviews": [], "count": 0}


def test_reviews_still_accepts_the_admin_key(client):
    response = client.get("/api/reviews", headers={"X-Admin-Key": ADMIN_KEY})
    assert response.status_code == 200


def test_reviews_rejects_a_wrong_admin_key(client):
    assert client.get("/api/reviews", headers={"X-Admin-Key": "nope"}).status_code == 401


def test_reviews_rejects_malformed_authorization(client):
    token = _token(client, ADMIN)
    for header in ("", "Bearer", "Bearer ", "Basic abc", token, f"bearer{token}"):
        response = client.get("/api/reviews", headers={"Authorization": header})
        assert response.status_code in (401, 403), header


def test_me_reports_admin_for_the_owner_only(client):
    for email, expected in ((ADMIN, True), (TESTER, False)):
        token = _token(client, email)
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == email
        assert body["is_admin"] is expected


def test_me_rejects_no_session(client):
    assert client.get("/api/auth/me").status_code == 401


def test_signup_endpoint_refuses_the_admin_address(client):
    response = client.post("/api/auth/signup",
                           json={"email": ADMIN, "password": "a-long-enough-password"})
    assert response.status_code == 403
