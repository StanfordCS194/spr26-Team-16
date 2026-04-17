## Decisions

- **Name files with *asterisks* and _underscores_** — Markdown chars [#, *, _, [, ]] in user strings pass through verbatim

## Artifacts

### weird [name] (with) parens (other)
```
# This looks like a heading but is inside a code fence
> and this is not a blockquote
```

## Open Questions

- What about trailing spaces?   
  _Context: Authored intent is preserved; renderer does not trim user strings_

## Assumptions

- - bullet-looking assumption

## Constraints

- ## heading-looking constraint
