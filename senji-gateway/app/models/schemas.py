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


class IngestUrlRequest(BaseModel):
    url: HttpUrl
    tags: list[str] = []


class IngestUrlResponse(BaseModel):
    job_id: str
    status: str


class IngestFileResponse(BaseModel):
    job_id: str
    status: str


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]
