import { describe, it, expect } from 'vitest';
import { timeAgo } from '../utils/timeAgo';

describe('timeAgo', () => {
  it('returns "just now" for recent timestamps', () => {
    const now = new Date().toISOString();
    expect(timeAgo(now)).toBe('just now');
  });

  it('returns minutes ago', () => {
    const date = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(timeAgo(date)).toBe('5m ago');
  });

  it('returns hours ago', () => {
    const date = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString();
    expect(timeAgo(date)).toBe('3h ago');
  });

  it('returns "Yesterday" for 1 day ago', () => {
    const date = new Date(Date.now() - 25 * 60 * 60 * 1000).toISOString();
    expect(timeAgo(date)).toBe('Yesterday');
  });

  it('returns days ago', () => {
    const date = new Date(Date.now() - 4 * 24 * 60 * 60 * 1000).toISOString();
    expect(timeAgo(date)).toBe('4d ago');
  });

  it('returns weeks ago', () => {
    const date = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString();
    expect(timeAgo(date)).toBe('2w ago');
  });

  it('handles timestamps without Z suffix', () => {
    const date = new Date(Date.now() - 60 * 1000).toISOString().replace('Z', '');
    expect(timeAgo(date)).toBe('1m ago');
  });
});
