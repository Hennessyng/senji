WIKI_SYSTEM_PROMPT = (
    "You write permanent Zettelkasten-style notes. "
    "Distill — do not summarize. Extract the single most valuable insight. "
    "Use [[wikilinks]] for every concept worth its own page. "
    "Output ONLY valid markdown. No code fences. No preamble. No meta-commentary."
)

WIKI_PROMPT_TEMPLATE = """Distill this article into a permanent note.

Title: {title}
Source: {source}

Content:
{content}

Write the note in exactly this shape (replace bracketed instructions with real content — no brackets in output):

## {title}

> [One sentence: the single most valuable insight from this article]

### Key Concepts
- [[Concept]] — one line on what it is or why it matters here
- [[Concept]] — one line on what it is or why it matters here
(3–6 concepts; use real concept names as wikilinks)

### Why It Matters
[1–2 sentences on significance or practical implication]

### Connections
- [[Related Topic]] — one line on how it connects
(2–4 connections; omit this section entirely if none apply)

---
source:: {source}
"""
