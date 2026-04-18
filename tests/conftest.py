import os

import pytest
import httpx

BASE_URL = os.environ.get("SENJI_BASE_URL", "http://localhost:8000")
TOKEN = os.environ.get("SENJI_TOKEN", "dev-token")


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(scope="session")
def api_client():
    client = httpx.Client(base_url=BASE_URL, timeout=120.0)
    yield client
    client.close()
