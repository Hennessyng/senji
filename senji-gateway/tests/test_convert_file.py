from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.main import app
from app.services.docling_client import DoclingResult

AUTH = {"Authorization": "Bearer dev-token"}

_DEFAULT_RESULT = DoclingResult(markdown="# Converted PDF")


def build_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
@patch("app.routes.convert.convert_file_svc", new_callable=AsyncMock, return_value=_DEFAULT_RESULT)
async def test_pdf_upload_returns_200(mock_convert) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/file",
            files={"file": ("test.pdf", b"fake pdf content", "application/pdf")},
            headers=AUTH,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["markdown"] == "# Converted PDF"
    assert data["title"] == "test.pdf"
    assert data["source"] == "test.pdf"
    assert data["media"] == []
    mock_convert.assert_called_once()


@pytest.mark.asyncio
@patch("app.routes.convert.convert_file_svc", new_callable=AsyncMock, return_value=_DEFAULT_RESULT)
async def test_docx_upload_returns_200(mock_convert) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/file",
            files={"file": ("report.docx", b"fake docx", "application/vnd.openxmlformats")},
            headers=AUTH,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["markdown"] == "# Converted PDF"
    assert data["title"] == "report.docx"
    mock_convert.assert_called_once()


@pytest.mark.asyncio
async def test_exe_upload_returns_415() -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/file",
            files={"file": ("malware.exe", b"evil bytes", "application/octet-stream")},
            headers=AUTH,
        )

    assert response.status_code == 415
    data = response.json()
    assert data["error"] == "unsupported_type"
    assert "pdf" in data["detail"].lower()


@pytest.mark.asyncio
@patch(
    "app.routes.convert.convert_file_svc",
    new_callable=AsyncMock,
    side_effect=httpx.ConnectError("connection refused"),
)
async def test_docling_down_returns_503(mock_convert) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/file",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            headers=AUTH,
        )

    assert response.status_code == 503
    data = response.json()
    assert data["error"] == "docling_unavailable"


@pytest.mark.asyncio
@patch(
    "app.routes.convert.convert_file_svc",
    new_callable=AsyncMock,
    side_effect=httpx.TimeoutException("read timed out"),
)
async def test_docling_timeout_returns_504(mock_convert) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/file",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            headers=AUTH,
        )

    assert response.status_code == 504
    data = response.json()
    assert data["error"] == "docling_timeout"
