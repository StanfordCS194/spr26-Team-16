import { describe, it, expect } from 'vitest';
import { formatContext } from '../utils/formatContext';

const MOCK_THREAD = {
  title: "Auth System Design",
  summary: "Discussed JWT-based authentication for the web app.",
  key_takeaways: [
    "Use JWT for stateless auth",
    "15-minute access tokens",
  ],
  open_threads: ["How to handle token revocation?"],
  artifacts: [
    {
      type: "code",
      language: "javascript",
      description: "Token generation utility",
      content: "const gen = () => jwt.sign({}, secret);",
    },
  ],
  tags: ["JWT", "auth"],
};

describe('formatContext', () => {
  it('starts with [Context from ContextHub]', () => {
    const result = formatContext(MOCK_THREAD);
    expect(result.startsWith('[Context from ContextHub]')).toBe(true);
  });

  it('ends with [End Context]', () => {
    const result = formatContext(MOCK_THREAD);
    expect(result.endsWith('[End Context]')).toBe(true);
  });

  it('includes the title', () => {
    const result = formatContext(MOCK_THREAD);
    expect(result).toContain('Continuing from a previous conversation: Auth System Design');
  });

  it('includes the summary', () => {
    const result = formatContext(MOCK_THREAD);
    expect(result).toContain('Discussed JWT-based authentication');
  });

  it('includes key takeaways', () => {
    const result = formatContext(MOCK_THREAD);
    expect(result).toContain('Key takeaways:');
    expect(result).toContain('- Use JWT for stateless auth');
    expect(result).toContain('- 15-minute access tokens');
  });

  it('includes open threads', () => {
    const result = formatContext(MOCK_THREAD);
    expect(result).toContain('Still open:');
    expect(result).toContain('- How to handle token revocation?');
  });

  it('includes artifacts when 3 or fewer', () => {
    const result = formatContext(MOCK_THREAD);
    expect(result).toContain('Artifacts from that conversation:');
    expect(result).toContain('[Token generation utility]');
    expect(result).toContain('```javascript');
    expect(result).toContain('const gen = () => jwt.sign({}, secret);');
  });

  it('shows note when more than 3 artifacts', () => {
    const manyArtifacts = {
      ...MOCK_THREAD,
      artifacts: [
        { type: "code", language: "js", description: "A", content: "a" },
        { type: "code", language: "js", description: "B", content: "b" },
        { type: "code", language: "js", description: "C", content: "c" },
        { type: "code", language: "js", description: "D", content: "d" },
      ],
    };
    const result = formatContext(manyArtifacts);
    expect(result).toContain('Note: 4 artifacts were produced');
    expect(result).not.toContain('Artifacts from that conversation:');
  });

  it('omits sections when arrays are empty', () => {
    const minimal = {
      title: "Test",
      summary: "Test summary",
      key_takeaways: [],
      open_threads: [],
      artifacts: [],
      tags: [],
    };
    const result = formatContext(minimal);
    expect(result).not.toContain('Key takeaways:');
    expect(result).not.toContain('Still open:');
    expect(result).not.toContain('Artifacts from that conversation:');
  });

  it('handles null/undefined arrays', () => {
    const partial = {
      title: "Test",
      summary: "Test summary",
    };
    const result = formatContext(partial);
    expect(result).toContain('[Context from ContextHub]');
    expect(result).toContain('[End Context]');
  });
});
