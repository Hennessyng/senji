#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from html.parser import HTMLParser

DEFAULT_URL = "https://www.mindstudio.ai/blog/build-monetize-ai-agents-business"
DEFAULT_OLLAMA = "http://10.1.1.222:11434"
DEFAULT_MODEL = "qwen2.5:3b"
CONTENT_CHAR_LIMIT = 4000
TIMEOUT = 120

WIKI_SYSTEM_PROMPT = """You write permanent Zettelkasten notes. Here is a complete example of correct output:

## Sourdough Bread

> Sourdough's flavor and preservation come from lactic acid bacteria fermenting flour starches over many hours.

### Key Concepts
- [[Lactic Acid Bacteria]] — convert sugars into acids that create flavor and inhibit spoilage
- [[Autolyse]] — pre-soak that develops gluten structure before kneading
- [[Hydration Ratio]] — water-to-flour percentage that determines crumb openness

### Why It Matters
Understanding fermentation kinetics lets bakers control sourness, rise time, and crumb structure consistently.

### Connections
- [[Wild Yeast]] — co-exists with bacteria in starter, producing CO2 that leavens the dough

---
source:: https://example.com/sourdough

Produce notes in exactly this format. Use [[double brackets]] around every concept name. The insight line MUST start with > (blockquote). No meta-commentary. No preamble. Stop after source::."""

WIKI_PROMPT_TEMPLATE = """Title: {title}
Source: {source}

Content:
{content}

Write the Zettelkasten note. Use "{title}" as the ## heading. End with:

---
source:: {source}"""


class _TextExtractor(HTMLParser):
    _SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []
        self._title: str = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self._title += data
            return
        stripped = data.strip()
        if stripped:
            self._parts.append(stripped)

    def get_text(self) -> str:
        return "\n".join(self._parts)

    def get_title(self) -> str:
        return self._title.strip()


def fetch_text(url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    parser = _TextExtractor()
    parser.feed(html)
    return parser.get_title() or url, parser.get_text()


def ollama_chat(base_url: str, model: str, system: str, user: str) -> str:
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "options": {
            "temperature": 0.2,
            "repeat_penalty": 1.3,
            "num_predict": 1024,
            "num_ctx": 8192,
        },
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    chunks: list[str] = []
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        for line in resp:
            line = line.decode().strip()
            if not line:
                continue
            data = json.loads(line)
            chunk = (data.get("message") or {}).get("content", "")
            if chunk:
                chunks.append(chunk)
    return "".join(chunks)


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE_RE = re.compile(r"^```[^\n]*\n(.*?)^```", re.DOTALL | re.MULTILINE)


def strip_think_blocks(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


def strip_code_fences(text: str) -> str:
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def validate(text: str) -> list[str]:
    failures: list[str] = []
    if not re.search(r"^## .+", text, re.MULTILINE):
        failures.append("missing ## heading")
    if not re.search(r"^> .+", text, re.MULTILINE):
        failures.append("missing > blockquote insight")
    if "[[" not in text:
        failures.append("no [[wikilinks]] found")
    if "source::" not in text:
        failures.append("missing source:: field")
    if "<think>" in text:
        failures.append("think block not stripped")
    if text.startswith("```"):
        failures.append("output wrapped in code fence")
    if len(text.strip()) < 100:
        failures.append(f"output too short ({len(text.strip())} chars)")
    return failures


def run_once(url: str, ollama: str, model: str) -> bool:
    print(f"\n--- Fetching {url} ---")
    try:
        title, text = fetch_text(url)
    except Exception as e:
        print(f"[FAIL] fetch error: {e}")
        return False

    content = text[:CONTENT_CHAR_LIMIT]
    print(f"  title: {title!r}  content: {len(content)} chars")

    user_msg = WIKI_PROMPT_TEMPLATE.format(
        title=title, source=url, content=content
    )

    print(f"--- Calling Ollama {ollama} model={model} ---")
    try:
        raw = ollama_chat(ollama, model, WIKI_SYSTEM_PROMPT, user_msg)
    except Exception as e:
        print(f"[FAIL] ollama error: {e}")
        return False

    cleaned = strip_code_fences(strip_think_blocks(raw))

    print("\n=== RAW OUTPUT (first 300 chars) ===")
    print(raw[:300] + ("..." if len(raw) > 300 else ""))
    print("\n=== CLEANED OUTPUT ===")
    print(cleaned)

    failures = validate(cleaned)
    if failures:
        print(f"\n[FAIL] validation: {', '.join(failures)}")
        return False

    print("\n[PASS] Karpathy-style wiki output validated.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--ollama", default=DEFAULT_OLLAMA)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--loop", type=int, default=1)
    args = parser.parse_args()

    for i in range(args.loop):
        if i > 0:
            print(f"\n--- iteration {i+1}/{args.loop} ---")
        ok = run_once(args.url, args.ollama, args.model)
        if ok:
            sys.exit(0)

    print("\n[ABORT] all iterations failed.")
    sys.exit(1)


if __name__ == "__main__":
    main()
