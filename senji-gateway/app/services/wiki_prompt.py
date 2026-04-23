WIKI_SYSTEM_PROMPT = (
    "You are a wiki curator. Output ONLY valid markdown. "
    "Do not wrap your output in triple backticks. "
    "Do not add explanations, apologies, or meta commentary."
)

WIKI_PROMPT_TEMPLATE = """You are a wiki curator. Summarise the following article into a structured wiki entry.

Title: {title}
Source: {source}
Language: {language}

Content:
{content}

Produce the output in this exact markdown shape (no code fences, no preamble):

## Summary
[2-3 paragraph summary of the article in plain prose]

## Key Concepts
- [concept 1 — one-line definition]
- [concept 2 — one-line definition]
- [concept 3 — one-line definition]

## Related
[[concept-link-1]]
[[concept-link-2]]
"""
