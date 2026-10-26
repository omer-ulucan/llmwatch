/**
 * Module: sse.ts
 * Purpose: POST a request and consume a Server-Sent Events response.
 * WHY: EventSource only supports GET without headers, and the old hand-rolled parser
 * lost events split across network chunks. This parser buffers until a blank line
 * (the SSE event delimiter), handles CRLF and multi-line data fields, and ignores
 * comments, so events are delivered whole regardless of chunking.
 */
import { useStore } from '@/store/useStore';

export class SSEParser {
  private buffer = '';

  /** Feeds a decoded chunk; returns the data payloads of every complete event. */
  push(chunk: string): string[] {
    this.buffer += chunk.replace(/\r\n?/g, '\n');
    const events: string[] = [];
    let boundary = this.buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const raw = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      const data = raw
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(line.startsWith('data: ') ? 6 : 5))
        .join('\n');
      if (data) events.push(data);
      boundary = this.buffer.indexOf('\n\n');
    }
    return events;
  }

  /** Any final event not followed by a blank line (servers sometimes omit it). */
  flush(): string[] {
    const rest = this.buffer;
    this.buffer = '';
    return rest.trim() ? this.push(`${rest}\n\n`) : [];
  }
}

export class HttpError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

/** POSTs JSON and calls onEvent with each parsed JSON event. */
export async function postSSE<T>(
  path: string,
  body: unknown,
  onEvent: (event: T) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = useStore.getState().token;
  const response = await fetch(`/api${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    let payload: unknown = null;
    let message = `Request failed (${response.status})`;
    try {
      payload = await response.json();
      if (payload && typeof payload === 'object' && 'error' in payload) {
        message = String((payload as { error: unknown }).error);
      }
    } catch {
      // Not JSON; keep the generic message.
    }
    if (response.status === 401) useStore.getState().logout();
    throw new HttpError(response.status, message, payload);
  }
  if (!response.body) throw new Error('The server returned no stream');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SSEParser();
  const emit = (data: string) => {
    try {
      onEvent(JSON.parse(data) as T);
    } catch {
      // Ignore malformed events instead of aborting the whole stream.
    }
  };
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parser.push(decoder.decode(value, { stream: true })).forEach(emit);
  }
  parser.push(decoder.decode()).forEach(emit);
  parser.flush().forEach(emit);
}
