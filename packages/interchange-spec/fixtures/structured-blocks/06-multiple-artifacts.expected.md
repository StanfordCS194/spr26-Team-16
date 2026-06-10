## Artifacts

### summaries table (schema)
```sql
CREATE TABLE summaries (
    id UUID PRIMARY KEY,
    push_id UUID NOT NULL,
    layer TEXT NOT NULL,
    content_json JSONB NOT NULL,
    content_markdown TEXT NOT NULL
);
```

### render helper (code)
```typescript
export function section(title: string, body: string): string {
  return `## ${title}\n\n${body}`;
}
```

### push pipeline milestones (outline)
```
- Module 1: interchange-spec
- Module 2: schema + migrations
- Module 3: auth
- Module 4: providers
```
