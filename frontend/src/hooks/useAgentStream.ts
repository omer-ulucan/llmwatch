/**
 * Hook: useAgentStream
 * Purpose: Custom React hook for POST + SSE streaming of agent execution events.
 * WHY: Standard EventSource only supports GET. For POST with a request body, we use
 * fetch() with ReadableStream to consume SSE events from the agent execution endpoint.
 * This hook manages the full lifecycle: connection, parsing, state updates, and cleanup.
 */
import { useState, useCallback, useRef } from 'react';
import { useStore } from '@/store/useStore';
import type { AgentEvent, AgentRunSummary, AgentRunRequest } from '@/types';

interface UseAgentStreamReturn {
  steps: AgentEvent[];
  isRunning: boolean;
  error: string | null;
  summary: AgentRunSummary | null;
  runAgent: (request: AgentRunRequest) => Promise<void>;
  reset: () => void;
}

export function useAgentStream(): UseAgentStreamReturn {
  const [steps, setSteps] = useState<AgentEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<AgentRunSummary | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    setSteps([]);
    setIsRunning(false);
    setError(null);
    setSummary(null);
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  }, []);

  const runAgent = useCallback(async (request: AgentRunRequest) => {
    // Reset state for new run
    setSteps([]);
    setError(null);
    setSummary(null);
    setIsRunning(true);

    const controller = new AbortController();
    abortRef.current = controller;

    const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const token = useStore.getState().token;

    try {
      const response = await fetch(`${baseUrl}/agent/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(request),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Agent request failed: ${response.status} ${errorText}`);
      }

      if (!response.body) {
        throw new Error('No response body for SSE stream');
      }

      // WHY: ReadableStream + TextDecoder is the standard way to consume SSE from fetch().
      // We manually parse the "data: {json}\n\n" SSE format.
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer (format: "data: {json}\n\n")
        const lines = buffer.split('\n');
        buffer = '';

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i];

          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6);
            try {
              const event: AgentEvent = JSON.parse(jsonStr);

              if (event.event_type === 'run_end') {
                // Parse the summary from the run_end content
                try {
                  const summaryData: AgentRunSummary = JSON.parse(event.content);
                  setSummary(summaryData);
                } catch {
                  // Content might not be valid JSON summary
                }
              } else if (event.event_type === 'error') {
                setError(event.content);
              }

              setSteps(prev => [...prev, event]);
            } catch {
              // Incomplete JSON, put it back in the buffer
              buffer = lines.slice(i).join('\n');
              break;
            }
          } else if (line === '') {
            // Empty line = end of SSE event, continue
            continue;
          } else {
            // Partial line, keep in buffer
            buffer += line;
            if (i < lines.length - 1) buffer += '\n';
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        // User cancelled — not an error
        return;
      }
      const message = err instanceof Error ? err.message : 'Unknown error during agent execution';
      setError(message);
    } finally {
      setIsRunning(false);
      abortRef.current = null;
    }
  }, []);

  return { steps, isRunning, error, summary, runAgent, reset };
}
