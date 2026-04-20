#!/usr/bin/env python3
"""Agentic self-test loop for senji.

Designed to be run by an LLM agent to verify the full stack is working.
Exits 0 = all green. Exits 1 = failures (with diagnostics + suggested fixes).

Usage:
    python tests/agentic_self_test.py
    python tests/agentic_self_test.py --verbose
    python tests/agentic_self_test.py --url https://example.com

The output is structured so an LLM can parse it and take corrective action:
  [PASS] test_name — brief description
  [FAIL] test_name — what went wrong
  [DIAG] diagnostic output (logs, container state)
  [FIX]  suggested fix action
  [SUMMARY] N passed, M failed
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any

# ── Config ────────────────────────────────────────────────────────────────────
GATEWAY_URL = "http://localhost:7878"
TOKEN = os.environ.get("SENJI_TOKEN", "dev-token")
AUTH = {"Authorization": f"Bearer {TOKEN}"}
TIMEOUT = 30.0
LARGE_HTML_SIZE = 400_000  # 400 KB — exercises the payload-size fix (express default limit is 100 KB)


# ── Result types ──────────────────────────────────────────────────────────────
@dataclass
class Result:
    name: str
    passed: bool
    detail: str = ""
    diag: str = ""
    fix: str = ""

    def label(self) -> str:
        return "PASS" if self.passed else "FAIL"


@dataclass
class Suite:
    results: list[Result] = field(default_factory=list)

    def add(self, r: Result) -> None:
        self.results.append(r)
        tag = f"\033[32m[PASS]\033[0m" if r.passed else f"\033[31m[FAIL]\033[0m"
        print(f"{tag} {r.name}", end="")
        if r.detail:
            print(f" — {r.detail}", end="")
        print()
        if not r.passed:
            if r.diag:
                for line in r.diag.strip().splitlines():
                    print(f"  [DIAG] {line}")
            if r.fix:
                print(f"  \033[33m[FIX]\033[0m  {r.fix}")

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def summary(self) -> str:
        total = len(self.results)
        return f"[SUMMARY] {self.passed}/{total} passed, {self.failed} failed"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _docker_logs(service: str, lines: int = 30) -> str:
    try:
        out = subprocess.run(
            ["docker", "compose", "logs", service, f"--tail={lines}"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=_project_root(),
        )
        return out.stdout + out.stderr
    except Exception as e:
        return f"(could not fetch logs: {e})"


def _docker_ps() -> str:
    try:
        out = subprocess.run(
            ["docker", "compose", "ps"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=_project_root(),
        )
        return out.stdout
    except Exception as e:
        return f"(could not fetch ps: {e})"


def _project_root() -> str:
    import os
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Response:
    """Minimal response wrapper for stdlib urllib."""
    def __init__(self, status_code: int, text: str, content: bytes):
        self.status_code = status_code
        self.text = text
        self.content = content
        self._json_cache = None

    def json(self) -> dict:
        if self._json_cache is None:
            self._json_cache = json.loads(self.text)
        return self._json_cache


def _get(path: str, headers: dict[str, str] | None = None, timeout: float = 30.0) -> _Response:
    """GET request using stdlib urllib."""
    url = f"{GATEWAY_URL}{path}"
    req = urllib.request.Request(url, method="GET")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
            return _Response(resp.status, content.decode("utf-8"), content)
    except urllib.error.HTTPError as e:
        content = e.read()
        return _Response(e.code, content.decode("utf-8"), content)


def _post(path: str, json_data: dict | None = None, headers: dict[str, str] | None = None, timeout: float = 30.0) -> _Response:
    """POST request using stdlib urllib."""
    url = f"{GATEWAY_URL}{path}"
    body = None
    if json_data:
        body = json.dumps(json_data).encode("utf-8")

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
            return _Response(resp.status, content.decode("utf-8"), content)
    except urllib.error.HTTPError as e:
        content = e.read()
        return _Response(e.code, content.decode("utf-8"), content)


# ── Test cases ────────────────────────────────────────────────────────────────
def test_gateway_reachable() -> Result:
    """Gateway must respond on port 7878."""
    name = "gateway_reachable"
    try:
        r = _get("/health", timeout=5.0)
        if r.status_code == 200 and r.json().get("status") == "ok":
            return Result(name, True, "HTTP 200 /health → {status: ok}")
        return Result(
            name, False,
            f"unexpected response: {r.status_code} {r.text[:200]}",
            fix="docker compose restart gateway",
        )
    except (urllib.error.URLError, TimeoutError) as e:
        return Result(
            name, False,
            f"connection failed: {e}",
            diag=_docker_ps(),
            fix="docker compose up -d && sleep 5",
        )


def test_auth_no_token() -> Result:
    """Request without token must return 401."""
    name = "auth_no_token_401"
    r = _post("/api/convert/html", json_data={"html": "<p>x</p>"}, timeout=10.0)
    if r.status_code == 401:
        return Result(name, True, "401 as expected")
    return Result(
        name, False,
        f"expected 401, got {r.status_code}: {r.text[:200]}",
        fix="Check auth middleware: senji-gateway/app/middleware/auth.py",
    )


def test_auth_wrong_token() -> Result:
    """Wrong token must return 401."""
    name = "auth_wrong_token_401"
    r = _post(
        "/api/convert/html",
        json_data={"html": "<p>x</p>"},
        headers={"Authorization": "Bearer wrong-token"},
        timeout=10.0,
    )
    if r.status_code == 401:
        return Result(name, True, "401 as expected")
    return Result(
        name, False,
        f"expected 401, got {r.status_code}: {r.text[:200]}",
        fix="Verify SENJI_TOKEN env var in .env matches dev-token",
    )


def test_html_small() -> Result:
    """Small HTML paste → markdown with frontmatter."""
    name = "html_small_convert"
    r = _post(
        "/api/convert/html",
        json_data={"html": "<h1>Test Title</h1><p>Hello world, senji works.</p>"},
        headers=AUTH,
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        return Result(
            name, False,
            f"HTTP {r.status_code}: {r.text[:300]}",
            diag=_docker_logs("gateway") + _docker_logs("readability"),
            fix="docker compose logs gateway readability",
        )
    body = r.json()
    md = body.get("markdown", "")
    if not md.startswith("---"):
        return Result(
            name, False,
            "markdown does not start with YAML frontmatter",
            diag=f"response: {json.dumps(body)[:400]}",
            fix="Check readability converter: senji-readability/src/converter.js",
        )
    if "Hello world" not in md and "Test Title" not in md:
        return Result(
            name, False,
            "content missing from markdown output",
            diag=f"markdown snippet: {md[:400]}",
        )
    return Result(name, True, f"frontmatter + content OK ({len(md)} chars)")


def test_html_large() -> Result:
    """Large HTML (~600 KB) must not trigger PayloadTooLargeError.

    Regression test for: express body-parser 100 KB default limit.
    Fix applied: express.json({ limit: '10mb' }) in senji-readability/src/index.js
    """
    name = "html_large_600kb"
    paragraph = "<p>" + ("Lorem ipsum dolor sit amet. " * 100) + "</p>"
    big_html = f"<article><h1>Large Page</h1>{''.join([paragraph] * 150)}</article>"
    assert len(big_html) > LARGE_HTML_SIZE, f"test data too small: {len(big_html)}"

    r = _post(
        "/api/convert/html",
        json_data={"html": big_html},
        headers=AUTH,
        timeout=TIMEOUT,
    )
    if r.status_code == 200:
        md = r.json().get("markdown", "")
        return Result(name, True, f"600 KB HTML → {len(md)} chars markdown OK")

    diag = _docker_logs("readability", lines=20)
    if "PayloadTooLargeError" in diag or "request entity too large" in diag:
        return Result(
            name, False,
            "PayloadTooLargeError from readability server",
            diag=diag,
            fix="Edit senji-readability/src/index.js: app.use(express.json({ limit: '10mb' })) then docker compose restart readability",
        )
    return Result(
        name, False,
        f"HTTP {r.status_code}: {r.text[:300]}",
        diag=diag,
        fix="docker compose logs readability",
    )


def test_url_convert(url: str = "https://example.com") -> Result:
    """URL conversion returns markdown with frontmatter."""
    name = f"url_convert({url})"
    r = _post(
        "/api/convert/url",
        json_data={"url": url},
        headers=AUTH,
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        diag = _docker_logs("gateway") + _docker_logs("readability")
        return Result(
            name, False,
            f"HTTP {r.status_code}: {r.text[:300]}",
            diag=diag,
            fix="docker compose logs gateway readability — look for KeyError or PayloadTooLargeError",
        )
    body = r.json()
    md = body.get("markdown", "")
    if not md.startswith("---"):
        return Result(
            name, False,
            "no YAML frontmatter in output",
            diag=f"response keys: {list(body.keys())}, snippet: {md[:200]}",
            fix="Check senji-readability/src/converter.js frontmatter generation",
        )
    if "source:" not in md:
        return Result(name, False, "frontmatter missing 'source:' field")
    return Result(name, True, f"OK — {len(md)} chars, title: {body.get('title', '?')!r}")


def test_empty_html_422() -> Result:
    """Empty HTML must return 422 Unprocessable Entity."""
    name = "html_empty_422"
    r = _post(
        "/api/convert/html",
        json_data={"html": ""},
        headers=AUTH,
        timeout=10.0,
    )
    if r.status_code == 422:
        return Result(name, True, "422 as expected")
    return Result(
        name, False,
        f"expected 422, got {r.status_code}: {r.text[:200]}",
        fix="Check input validation in senji-gateway/app/routes/convert.py",
    )


def test_invalid_url_error() -> Result:
    """Unreachable URL must return an error (not 200)."""
    name = "url_invalid_returns_error"
    r = _post(
        "/api/convert/url",
        json_data={"url": "https://this.domain.absolutely.does.not.exist.invalid"},
        headers=AUTH,
        timeout=TIMEOUT,
    )
    if r.status_code in (422, 400, 500, 502, 503, 504):
        body = r.json()
        has_error_key = "error" in body or "detail" in body
        if has_error_key:
            return Result(name, True, f"HTTP {r.status_code} with error key")
    return Result(
        name, False,
        f"expected error status, got {r.status_code}: {r.text[:200]}",
        fix="Check fetch error handling in senji-gateway/app/services/fetcher.py",
    )


def test_readability_direct() -> Result:
    """Readability service must respond on its internal health endpoint."""
    name = "readability_health_direct"
    try:
        # readability is internal — test via docker exec
        out = subprocess.run(
            ["docker", "exec", "senji-readability-1", "node", "-e",
             "require('http').get('http://localhost:3000/health',r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>{process.stdout.write(d);process.exit(0)})})"],
            capture_output=True, text=True, timeout=10, cwd=_project_root(),
        )
        if '"status":"ok"' in out.stdout or '"status": "ok"' in out.stdout:
            return Result(name, True, "readability /health → ok")
        return Result(
            name, False,
            f"unexpected output: {out.stdout[:200]} {out.stderr[:200]}",
            diag=_docker_logs("readability", 10),
            fix="docker compose restart readability",
        )
    except Exception as e:
        return Result(
            name, False,
            f"docker exec failed: {e}",
            diag=_docker_ps(),
            fix="docker compose up -d readability",
        )


# ── Runner ────────────────────────────────────────────────────────────────────
def run(url: str, verbose: bool) -> int:
    suite = Suite()
    print(f"\n\033[1m=== senji agentic self-test ===\033[0m")
    print(f"Gateway: {GATEWAY_URL}  Token: {TOKEN}\n")

    gw = test_gateway_reachable()
    suite.add(gw)
    if not gw.passed:
        print("\n[ABORT] Gateway unreachable — skipping remaining tests.")
        print(suite.summary())
        return 1

    suite.add(test_readability_direct())
    suite.add(test_auth_no_token())
    suite.add(test_auth_wrong_token())
    suite.add(test_html_small())
    suite.add(test_html_large())
    suite.add(test_empty_html_422())
    suite.add(test_url_convert(url))
    suite.add(test_invalid_url_error())

    print(f"\n{suite.summary()}")
    if verbose and suite.failed > 0:
        print("\n--- Full container state ---")
        print(_docker_ps())
        print("\n--- Gateway logs (last 30 lines) ---")
        print(_docker_logs("gateway", 30))
        print("\n--- Readability logs (last 30 lines) ---")
        print(_docker_logs("readability", 30))

    return 0 if suite.failed == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Senji agentic self-test loop")
    parser.add_argument("--url", default="https://example.com", help="URL to test conversion")
    parser.add_argument("--verbose", action="store_true", help="Dump logs on failure")
    parser.add_argument(
        "--loop", type=int, default=1, metavar="N",
        help="Run N times with 5s pause between (for LLM self-fix loops)",
    )
    args = parser.parse_args()

    for i in range(args.loop):
        if i > 0:
            print(f"\n\033[2m--- loop iteration {i+1}/{args.loop}, waiting 5s ---\033[0m")
            time.sleep(5)
        code = run(args.url, args.verbose)
        if code == 0:
            print("\033[32m✓ All tests passed.\033[0m\n")
        else:
            print("\033[31m✗ Tests failed. See [FIX] hints above.\033[0m\n")
            sys.exit(code)

    sys.exit(0)


if __name__ == "__main__":
    main()
