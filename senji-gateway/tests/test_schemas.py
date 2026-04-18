import json

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    ConvertHTMLRequest,
    ConvertResponse,
    ConvertURLRequest,
    ErrorResponse,
    HealthResponse,
    MediaItem,
)


def test_convert_url_request_accepts_valid_url() -> None:
    request = ConvertURLRequest.model_validate({"url": "https://example.com"})

    assert str(request.url) == "https://example.com/"


def test_convert_url_request_rejects_invalid_url() -> None:
    with pytest.raises(ValidationError):
        ConvertURLRequest.model_validate({"url": "not-a-url"})


def test_convert_response_serializes_all_required_fields() -> None:
    response = ConvertResponse(
        markdown="# Test",
        title="Test",
        source="https://example.com",
        media=[],
    )

    payload = json.loads(response.model_dump_json())

    assert set(payload) == {"markdown", "title", "source", "media"}
    assert payload["markdown"] == "# Test"
    assert payload["title"] == "Test"
    assert payload["source"] == "https://example.com"
    assert payload["media"] == []


def test_convert_html_request_allows_missing_source_url() -> None:
    request = ConvertHTMLRequest(html="<p>test</p>")

    assert request.html == "<p>test</p>"
    assert request.source_url is None


def test_error_response_serializes_correctly() -> None:
    response = ErrorResponse(error="timeout", detail="request timed out")

    assert response.model_dump() == {
        "error": "timeout",
        "detail": "request timed out",
    }


def test_health_response_serializes_correctly() -> None:
    response = HealthResponse(status="ok", services={"readability": "ok"})

    assert response.model_dump() == {
        "status": "ok",
        "services": {"readability": "ok"},
    }


def test_media_item_serializes_correctly() -> None:
    media_item = MediaItem(
        filename="article-img-1.jpg",
        content_type="image/jpeg",
        data="YmFzZTY0",
    )

    assert media_item.model_dump() == {
        "filename": "article-img-1.jpg",
        "content_type": "image/jpeg",
        "data": "YmFzZTY0",
    }
