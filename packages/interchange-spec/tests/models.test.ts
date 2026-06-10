import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  validateConversation,
  validateStructuredBlock,
  makeValidator,
} from "../src/ajv.js";

const FIXTURES = resolve(__dirname, "..", "fixtures");

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8"));
}

describe("conversation fixtures", () => {
  const dir = resolve(FIXTURES, "conversations");
  const paths = readdirSync(dir).filter((f) => f.endsWith(".json"));

  it("at least one conversation fixture exists", () => {
    expect(paths.length).toBeGreaterThan(0);
  });

  for (const p of paths) {
    it(`validates ${p}`, () => {
      const obj = readJson(resolve(dir, p));
      expect(validateConversation(obj)).toBe(true);
    });
  }
});

describe("structured-block fixtures", () => {
  const dir = resolve(FIXTURES, "structured-blocks");
  const paths = readdirSync(dir).filter((f) => f.endsWith(".json"));

  it("at least 10 structured-block fixtures exist", () => {
    expect(paths.length).toBeGreaterThanOrEqual(10);
  });

  for (const p of paths) {
    it(`validates ${p}`, () => {
      const obj = readJson(resolve(dir, p));
      expect(validateStructuredBlock(obj)).toBe(true);
    });
  }
});

describe("schema rejections", () => {
  const v = makeValidator("structured-block");

  it("rejects wrong spec_version", () => {
    expect(
      v({
        spec_version: "ch.v0.2",
        decisions: [],
        artifacts: [],
        open_questions: [],
        assumptions: [],
        constraints: [],
      }),
    ).toBe(false);
  });

  it("rejects extra properties", () => {
    expect(
      v({
        spec_version: "ch.v0.1",
        decisions: [],
        artifacts: [],
        open_questions: [],
        assumptions: [],
        constraints: [],
        surprise: 1,
      }),
    ).toBe(false);
  });

  it("rejects unknown artifact kind", () => {
    expect(
      v({
        spec_version: "ch.v0.1",
        decisions: [],
        artifacts: [{ kind: "spreadsheet", name: "x", body: "" }],
        open_questions: [],
        assumptions: [],
        constraints: [],
      }),
    ).toBe(false);
  });
});
