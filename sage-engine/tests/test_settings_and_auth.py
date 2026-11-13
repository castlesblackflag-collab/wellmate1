import pytest
from pydantic import ValidationError

import engine.auth as auth
from tests.conftest import make_settings


def test_auth_bypass_refused_in_production():
    with pytest.raises(ValidationError, match="AUTH_DISABLED"):
        make_settings(environment="production", auth_disabled=True)


def test_fake_model_refused_in_production():
    with pytest.raises(ValidationError, match="fake"):
        make_settings(environment="production", chat_provider="fake")


def test_blank_env_values_count_as_unset(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("NCBI_API_KEY", "")
    s = make_settings()
    assert s.supabase_url is None
    assert s.ncbi_api_key is None
    assert s.supabase_configured is False


def test_secrets_never_print():
    s = make_settings(supabase_service_key="sk-very-secret")
    assert "sk-very-secret" not in repr(s)
    assert "sk-very-secret" not in str(s.model_dump())


def test_valid_token_gives_uid(client_factory, monkeypatch):
    seen = {}

    def fake_verify(token, project_id):
        seen["token"], seen["project"] = token, project_id
        return {"uid": "firebase-uid-123", "email": "a@example.com"}

    monkeypatch.setattr(auth, "verify_firebase_token", fake_verify)
    r = client_factory().post("/v1/chat", json={"message": "hi"}, headers={"Authorization": "Bearer tok"})
    # Signed in fine, so we get past auth to the not-built-yet response.
    assert r.status_code == 501
    assert seen == {"token": "tok", "project": "wellmate-i"}


def test_bad_token_is_401(client_factory, monkeypatch):
    def reject(token, project_id):
        raise ValueError("expired")

    monkeypatch.setattr(auth, "verify_firebase_token", reject)
    r = client_factory().post("/v1/chat", json={"message": "hi"}, headers={"Authorization": "Bearer old"})
    assert r.status_code == 401
