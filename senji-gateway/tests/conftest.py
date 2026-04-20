import os

import httpx
import pytest

# E2E tests run against live Docker services on localhost:8000
# Configured via environment variables for CI environments
BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")
AUTH_TOKEN = os.getenv("SENJI_TOKEN", "dev-token")


@pytest.fixture
async def api_client() -> httpx.AsyncClient:
    """
    HTTP client configured for E2E tests.
    Connects to real Docker services (not mocked).
    """
    transport = httpx.AsyncHTTPTransport(
        verify=False  # Allow self-signed certs in test environments
    )
    client = httpx.AsyncClient(transport=transport, base_url=BASE_URL, timeout=30.0)
    yield client
    await client.aclose()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Bearer token for authenticated endpoints."""
    return {"Authorization": f"Bearer {AUTH_TOKEN}"}


@pytest.fixture
def base_url() -> str:
    """Base URL of the API gateway."""
    return BASE_URL
