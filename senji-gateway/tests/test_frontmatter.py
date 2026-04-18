from datetime import datetime

from app.services.frontmatter import generate_frontmatter, prepend_frontmatter


def test_generate_frontmatter_has_required_fields() -> None:
    result = generate_frontmatter(
        source="https://example.com/post",
        title="Example Title",
        clip_type="web",
    )

    assert result.startswith("---\n")
    assert "\n---\n" in result
    assert 'source: "https://example.com/post"' in result
    assert 'title: "Example Title"' in result
    assert "\ntype: web\n" in result
    assert "\ntags:\n" in result
    assert "\n  - clipping\n" in result
    assert "\n  - inbox\n" in result
    assert "\n  - web\n" in result


def test_clipped_field_is_valid_iso8601_utc_datetime() -> None:
    result = generate_frontmatter(
        source="https://example.com",
        title="Example",
        clip_type="web",
    )

    clipped_line = next(line for line in result.splitlines() if line.startswith("clipped: "))
    clipped = clipped_line.removeprefix("clipped: ")

    parsed = datetime.strptime(clipped, "%Y-%m-%dT%H:%M:%SZ")
    assert parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == clipped


def test_title_with_quotes_and_colon_is_yaml_escaped() -> None:
    result = generate_frontmatter(
        source="https://example.com",
        title='He said "hello": world',
        clip_type="web",
    )

    assert 'title: "He said \\\"hello\\\": world"' in result


def test_different_clip_types_set_type_and_tags() -> None:
    web_result = generate_frontmatter("https://example.com", "Example", "web")
    pdf_result = generate_frontmatter("report.pdf", "report.pdf", "pdf")

    assert "\ntype: web\n" in web_result
    assert "\n  - web\n" in web_result
    assert "\ntype: pdf\n" in pdf_result
    assert "\n  - pdf\n" in pdf_result


def test_prepend_frontmatter_adds_blank_line_before_markdown() -> None:
    result = prepend_frontmatter(
        markdown="# Body",
        source="https://example.com",
        title="Example",
        clip_type="web",
    )

    assert result.startswith("---\n")
    assert result.endswith("\n\n# Body")
