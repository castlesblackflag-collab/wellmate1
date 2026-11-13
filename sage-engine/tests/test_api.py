from engine import __version__
from engine.errors import UpstreamError


def test_health_is_ok_and_tags_request_id(client_factory):
    client = client_factory()
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": __version__, "environment": "local"}
    assert r.headers.get("X-Request-ID")


def test_incoming_request_id_is_kept(client_factory):
    r = client_factory().get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"


def test_ready_reports_missing_config_without_leaking_values(client_factory):
    client = client_factory(ncbi_api_key="super-secret-value")
    r = client.get("/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["ready"] is False
    assert body["checks"]["supabase"]["ok"] is False
    assert body["optional_keys_present"]["ncbi_api_key"] is True
    assert "super-secret-value" not in r.text


def test_chat_requires_sign_in(client_factory):
    r = client_factory().post("/v1/chat", json={"message": "hello"})
    assert r.status_code == 401
    err = r.json()["error"]
    assert err["code"] == "unauthorized"
    assert err["request_id"] == r.headers["X-Request-ID"]


def test_chat_rejects_malformed_body_with_standard_shape(client_factory):
    from engine.container import get_sage

    client = client_factory(auth_disabled=True)
    client.app.dependency_overrides[get_sage] = lambda: None  # as if chat were switched on
    r = client.post("/v1/chat", json={"message": ""})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"


def test_chat_is_switched_off_until_built(client_factory):
    r = client_factory(auth_disabled=True).post("/v1/chat", json={"message": "hello"})
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "not_implemented"


def test_unexpected_errors_are_logged_and_shaped(client_factory, caplog):
    client = client_factory()

    @client.app.get("/boom")
    async def boom():
        raise RuntimeError("database exploded")

    @client.app.get("/upstream")
    async def upstream():
        raise UpstreamError("vertex timeout after 30s")

    r = client.get("/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "database exploded" not in r.text  # technical detail stays in the logs
    assert r.json()["error"]["request_id"] == r.headers["X-Request-ID"] != "-"
    logged = [rec for rec in caplog.records if rec.getMessage() == "unhandled_error"]
    assert logged and logged[0].exc_info  # full traceback is in the log

    r = client.get("/upstream")
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "upstream_error"


def test_unknown_route_uses_standard_shape(client_factory):
    r = client_factory().get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_cors_allows_app_origin(client_factory):
    r = client_factory().options(
        "/v1/chat",
        headers={"Origin": "https://thewellmate.live", "Access-Control-Request-Method": "POST"},
    )
    assert r.headers.get("access-control-allow-origin") == "https://thewellmate.live"


def test_docs_hidden_in_production(client_factory):
    assert client_factory(environment="production").get("/docs").status_code == 404
