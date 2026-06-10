import { describe, expect, it } from "vitest";
import { renderStructuredBlock } from "../src/renderer.js";
import type { StructuredBlockV0 } from "../src/models.js";

function block(overrides: Partial<StructuredBlockV0> = {}): StructuredBlockV0 {
  return {
    spec_version: "ch.v0.1",
    decisions: [],
    artifacts: [],
    open_questions: [],
    assumptions: [],
    constraints: [],
    ...overrides,
  };
}

describe("renderStructuredBlock", () => {
  it("empty block renders empty string", () => {
    expect(renderStructuredBlock(block())).toBe("");
  });

  it("renders single decision", () => {
    const out = renderStructuredBlock(
      block({ decisions: [{ title: "Use Postgres", rationale: "pgvector native" }] }),
    );
    expect(out).toBe("## Decisions\n\n- **Use Postgres** \u2014 pgvector native\n");
  });

  it("inserts blank line between sections", () => {
    const out = renderStructuredBlock(
      block({
        decisions: [{ title: "Ship beta", rationale: "pressure" }],
        assumptions: ["single user"],
      }),
    );
    expect(out.includes("\n\n## Assumptions\n")).toBe(true);
    expect(out.endsWith("- single user\n")).toBe(true);
  });

  it("preserves artifact trailing-newline semantics", () => {
    const out = renderStructuredBlock(
      block({ artifacts: [{ kind: "code", name: "fn", body: "print(1)" }] }),
    );
    expect(out.includes("```\nprint(1)\n```\n")).toBe(true);
  });

  it("does not double-newline when artifact body ends with newline", () => {
    const out = renderStructuredBlock(
      block({ artifacts: [{ kind: "code", name: "fn", body: "print(1)\n" }] }),
    );
    expect(out.includes("print(1)\n```")).toBe(true);
    expect(out.includes("print(1)\n\n```")).toBe(false);
  });

  it("uses bare fence when language is omitted", () => {
    const out = renderStructuredBlock(
      block({ artifacts: [{ kind: "other", name: "note", body: "hi" }] }),
    );
    expect(out.includes("```\nhi\n```")).toBe(true);
  });

  it("renders open question with and without context", () => {
    const out = renderStructuredBlock(
      block({
        open_questions: [
          { question: "What cache TTL?", context: "pulls are hot" },
          { question: "Unit of concurrency?" },
        ],
      }),
    );
    expect(out.includes("- What cache TTL?\n  _Context: pulls are hot_\n")).toBe(true);
    expect(out.includes("- Unit of concurrency?\n")).toBe(true);
    expect(out.includes("- Unit of concurrency?\n  _Context:")).toBe(false);
  });

  it("normalizes to NFC", () => {
    const decomposed = "e\u0301"; // e + COMBINING ACUTE
    const out = renderStructuredBlock(block({ assumptions: [`caf${decomposed}`] }));
    expect(out).toBe(out.normalize("NFC"));
    expect(out.includes("caf\u00e9")).toBe(true);
    expect(out.includes(decomposed)).toBe(false);
  });

  it("ends with a single newline when non-empty", () => {
    const out = renderStructuredBlock(block({ constraints: ["x"] }));
    expect(out.endsWith("\n")).toBe(true);
    expect(out.endsWith("\n\n")).toBe(false);
  });

  it("omits empty sections entirely", () => {
    const out = renderStructuredBlock(
      block({ decisions: [{ title: "T", rationale: "R" }] }),
    );
    expect(out.includes("## Artifacts")).toBe(false);
    expect(out.includes("## Assumptions")).toBe(false);
    expect(out.includes("## Constraints")).toBe(false);
    expect(out.includes("## Open Questions")).toBe(false);
  });
});
