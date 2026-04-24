"""E2E integration tests — require live Docker services.

Run with: SENJI_TOKEN=your-token pytest tests/test_e2e.py -v --timeout=120
Services must be running: docker compose up -d
"""
import os

import httpx
import pytest

pytestmark = pytest.mark.timeout(120)

AUTH = {"Authorization": "Bearer dev-token"}
NO_AUTH: dict = {}
BAD_AUTH = {"Authorization": "Bearer wrong-token"}


def _skip_if_down(client: httpx.Client) -> None:
    """Skip test if gateway is not reachable."""
    try:
        client.get("/health", timeout=3)
    except (httpx.ConnectError, httpx.TimeoutException):
        pytest.skip("Gateway not reachable — start with: docker compose up -d")


class TestHealth:
    def test_health_returns_ok(self, api_client):
        _skip_if_down(api_client)
        r = api_client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestAuth:
    def test_no_token_returns_401(self, api_client):
        _skip_if_down(api_client)
        r = api_client.post("/api/convert/html", json={"html": "<p>test</p>"})
        assert r.status_code == 401

    def test_wrong_token_returns_401(self, api_client):
        _skip_if_down(api_client)
        r = api_client.post(
            "/api/convert/html",
            json={"html": "<p>test</p>"},
            headers=BAD_AUTH,
        )
        assert r.status_code == 401


class TestHtmlConvert:
    def test_html_paste_returns_markdown(self, api_client):
        _skip_if_down(api_client)
        r = api_client.post(
            "/api/convert/html",
            json={"html": "<h1>Test Title</h1><p>Hello world</p>"},
            headers=AUTH,
        )
        assert r.status_code == 200
        body = r.json()
        assert "markdown" in body
        assert "Hello world" in body["markdown"] or "Test Title" in body["markdown"]
        assert "title" in body
        assert "source" in body
        assert "media" in body

    def test_html_frontmatter_present(self, api_client):
        _skip_if_down(api_client)
        r = api_client.post(
            "/api/convert/html",
            json={"html": "<h1>Frontmatter Check</h1><p>Content</p>"},
            headers=AUTH,
        )
        assert r.status_code == 200
        markdown = r.json()["markdown"]
        assert markdown.startswith("---"), "Response must start with YAML frontmatter"
        assert "source:" in markdown
        assert "title:" in markdown
        assert "type:" in markdown

    def test_empty_html_returns_422(self, api_client):
        _skip_if_down(api_client)
        r = api_client.post("/api/convert/html", json={"html": ""}, headers=AUTH)
        assert r.status_code == 422


class TestUrlConvert:
    def test_url_conversion_returns_markdown(self, api_client):
        _skip_if_down(api_client)
        r = api_client.post(
            "/api/convert/url",
            json={"url": "https://example.com"},
            headers=AUTH,
            timeout=30.0,
        )
        assert r.status_code == 200
        body = r.json()
        assert "markdown" in body
        assert len(body["markdown"]) > 0
        assert "media" in body

    def test_invalid_url_returns_error(self, api_client):
        _skip_if_down(api_client)
        r = api_client.post(
            "/api/convert/url",
            json={"url": "https://this.domain.does.not.exist.invalid"},
            headers=AUTH,
            timeout=30.0,
        )
        assert r.status_code in (422, 500, 502, 503, 504)
        body = r.json()
        assert "error" in body or "detail" in body


class TestFileUpload:
    def test_unsupported_file_type_returns_415(self, api_client, tmp_path):
        _skip_if_down(api_client)
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")
        r = api_client.post(
            "/api/convert/file",
            files={"file": ("test.txt", txt_file.read_bytes(), "text/plain")},
            headers=AUTH,
        )
        assert r.status_code == 415

    def test_pdf_upload_returns_markdown(self, api_client):
        _skip_if_down(api_client)
        pdf_path = os.path.join(os.path.dirname(__file__), "fixtures", "test.pdf")
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        r = api_client.post(
            "/api/convert/file",
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
            headers=AUTH,
            timeout=120.0,
        )
        # Docling may not be running — accept 200 or 503
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            assert "markdown" in r.json()
