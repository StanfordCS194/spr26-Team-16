## Decisions

- **Drop message_refs in first pass** — Summarizer won't emit them reliably at v0
- **Skip question context when unsure** — Better to omit than to guess

## Open Questions

- Is context always recoverable post-hoc?
- Do we validate context length?
