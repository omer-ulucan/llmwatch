import { describe, expect, it, vi } from 'vitest';

// sse.ts imports the store (which touches localStorage); stub it for node.
vi.mock('@/store/useStore', () => ({ useStore: { getState: () => ({ token: null, logout: () => {} }) } }));

const { SSEParser } = await import('./sse');

describe('SSEParser', () => {
  it('parses complete events', () => {
    const p = new SSEParser();
    expect(p.push('data: {"a":1}\n\ndata: {"b":2}\n\n')).toEqual(['{"a":1}', '{"b":2}']);
  });

  it('keeps events split across chunks', () => {
    // Regression: the old hook lost events whose JSON spanned two network chunks.
    const p = new SSEParser();
    expect(p.push('data: {"text":"hel')).toEqual([]);
    expect(p.push('lo"}\n')).toEqual([]);
    expect(p.push('\ndata: {"x"')).toEqual(['{"text":"hello"}']);
    expect(p.push(':1}\n\n')).toEqual(['{"x":1}']);
  });

  it('handles CRLF line endings and "data:" without a space', () => {
    const p = new SSEParser();
    expect(p.push('data:{"a":1}\r\n\r\n')).toEqual(['{"a":1}']);
  });

  it('joins multi-line data fields and ignores comments and other fields', () => {
    const p = new SSEParser();
    expect(p.push(': keep-alive\n\nevent: msg\ndata: line1\ndata: line2\n\n')).toEqual(['line1\nline2']);
  });

  it('flushes a trailing event without the final blank line', () => {
    const p = new SSEParser();
    expect(p.push('data: {"last":true}')).toEqual([]);
    expect(p.flush()).toEqual(['{"last":true}']);
  });
});
