import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { renderStructuredBlock } from "../src/renderer.js";
import type { StructuredBlockV0 } from "../src/models.js";

const FIXTURES = resolve(__dirname, "..", "fixtures", "structured-blocks");

const jsonFiles = readdirSync(FIXTURES).filter((f) => f.endsWith(".json"));

describe("golden fixtures — TS renderer matches expected.md bytes", () => {
  it("has at least 10 fixtures", () => {
    expect(jsonFiles.length).toBeGreaterThanOrEqual(10);
  });

  for (const jsonFile of jsonFiles) {
    const name = jsonFile.replace(/\.json$/, "");
    it(`${name}`, () => {
      const block = JSON.parse(readFileSync(resolve(FIXTURES, jsonFile), "utf8")) as StructuredBlockV0;
      const expected = readFileSync(resolve(FIXTURES, `${name}.expected.md`), "utf8");
      const actual = renderStructuredBlock(block);
      expect(actual).toBe(expected);
    });
  }
});
