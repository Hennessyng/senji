from pydantic import BaseModel, HttpUrl


class ConvertURLRequest(BaseModel):
    url: HttpUrl


class ConvertHTMLRequest(BaseModel):
    html: str
    source_url: str | None = None


class MediaItem(BaseModel):
    filename: str
    content_type: str
    data: str


class ConvertResponse(BaseModel):
    markdown: str
    title: str
    source: str
    media: list[MediaItem] = []


class ErrorResponse(BaseModel):
    error: str
    detail: str


class HealthResponse(BaseModel):
    status: str
    services: dict[str, str]


class IngestResponse(BaseModel):
    markdown: str
    title: str
    source: str
    author: str | None = None
    language: str | None = None
    publish_date: str | None = None
