## Decisions

- **Quote raw markdown in rationales** — Inline code like `render_structured_block` and lists:
- one
- two
must pass through verbatim
- **Preserve **bold** and *italic* as-is** — The renderer does not escape; summarizer output already assumes markdown rendering downstream.

## Open Questions

- Should rationales allow code fences ``` inside?
  _Context: A body containing ``` would collide with artifact fences if copy-pasted; avoid in prompts._
