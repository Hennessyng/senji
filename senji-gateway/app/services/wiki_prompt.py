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

WIKI_PROMPT_TEMPLATE = """/no_think
Title: {title}
Source: {source}

Content:
{content}

Write the Zettelkasten note. Use "{title}" as the ## heading. End with:

---
source:: {source}"""
