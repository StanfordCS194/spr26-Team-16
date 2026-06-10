/**
 * Structured-block → markdown renderer.
 *
 * Authoritative spec: contexthub/docs/renderer-spec.md
 * MUST produce byte-identical output to python/contexthub_interchange/renderer.py
 * for every valid StructuredBlockV0. Golden fixtures enforce this.
 */

import type { StructuredBlockV0 } from "./models.js";

const EM_DASH = "\u2014";

export function renderStructuredBlock(block: StructuredBlockV0): string {
  const sections: string[] = [];

  if (block.decisions.length > 0) {
    let body = "";
    for (const d of block.decisions) {
      body += `- **${d.title}** ${EM_DASH} ${d.rationale}\n`;
    }
    sections.push("## Decisions\n\n" + body);
  }

  if (block.artifacts.length > 0) {
    let body = "";
    block.artifacts.forEach((a, i) => {
      if (i > 0) body += "\n";
      body += `### ${a.name} (${a.kind})\n`;
      body += "```" + (a.language ?? "") + "\n";
      body += a.body;
      if (!a.body.endsWith("\n")) body += "\n";
      body += "```\n";
    });
    sections.push("## Artifacts\n\n" + body);
  }

  if (block.open_questions.length > 0) {
    let body = "";
    for (const q of block.open_questions) {
      body += `- ${q.question}\n`;
      if (q.context !== undefined && q.context !== "") {
        body += `  _Context: ${q.context}_\n`;
      }
    }
    sections.push("## Open Questions\n\n" + body);
  }

  if (block.assumptions.length > 0) {
    let body = "";
    for (const a of block.assumptions) body += `- ${a}\n`;
    sections.push("## Assumptions\n\n" + body);
  }

  if (block.constraints.length > 0) {
    let body = "";
    for (const c of block.constraints) body += `- ${c}\n`;
    sections.push("## Constraints\n\n" + body);
  }

  if (sections.length === 0) return "";

  let out = sections.join("\n");
  out = out.replace(/\n+$/, "") + "\n";
  return out.normalize("NFC");
}
