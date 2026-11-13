import pytest
from fastapi.testclient import TestClient

from engine.settings import Settings, get_settings
from main import create_app


def make_settings(**overrides) -> Settings:
    # _env_file=None keeps a developer's own .env from leaking into tests.
    return Settings(_env_file=None, **overrides)


@pytest.fixture
def client_factory():
    def _make(**overrides) -> TestClient:
        settings = make_settings(**overrides)
        app = create_app(settings)
        app.dependency_overrides[get_settings] = lambda: settings
        return TestClient(app, raise_server_exceptions=False)

    return _make
