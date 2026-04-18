from datetime import datetime, timezone


def _yaml_escape(value: str) -> str:
    """Escape a string for use as a YAML double-quoted scalar."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def generate_frontmatter(
    source: str,
    title: str,
    clip_type: str,
    extra_tags: list[str] | None = None,
) -> str:
    """Generate YAML frontmatter block."""
    tags = ["clipping", "inbox", clip_type] + (extra_tags or [])
    tag_lines = "\n".join(f"  - {tag}" for tag in tags)
    clipped = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""---
source: \"{_yaml_escape(source)}\"
title: \"{_yaml_escape(title)}\"
clipped: {clipped}
type: {clip_type}
tags:
{tag_lines}
---
"""


def prepend_frontmatter(markdown: str, source: str, title: str, clip_type: str) -> str:
    """Prepend frontmatter to markdown content."""
    return generate_frontmatter(source, title, clip_type) + "\n" + markdown
