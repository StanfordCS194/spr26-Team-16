## Decisions

- **Adopt ARQ for async push** — Async job queue on Redis; lightweight + Python-native
- **Workspace-scoped search in v0** — Simpler RLS story; multi-workspace search lands with teams

## Artifacts

### pushes table (schema)
```sql
CREATE TABLE pushes (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);
```

### api client sketch (code)
```python
async def create_push(client, payload):
    return await client.post('/v1/pushes', json=payload)
```

## Open Questions

- Do we cache pull responses?
  _Context: Latency target is 200ms at p95; cache would help if repeats are common_
- Multi-pull ordering: chronological or user-chosen?

## Assumptions

- Single-user workspaces in v0
- Claude.ai is the only source platform at beta launch

## Constraints

- Haiku context window bounds conversation size per push
- Supabase free-tier row limits during beta
