/**
 * Hook: useAgentStream
 * Purpose: Runs the agent and collects its SSE events.
 * WHY: Uses the shared SSE client (events split across network chunks are no longer
 * lost). Stop aborts the stream and asks the server to cancel the run, so the trace
 * is saved as cancelled instead of continuing to spend tokens.
 */
import { useCallback, useRef, useState } from 'react';
import { agentApi } from '@/api/agent';
import { getErrorMessage } from '@/api/errors';
import { postSSE } from '@/lib/sse';
import type { AgentEvent, AgentRunRequest, AgentRunSummary } from '@/types';

export function useAgentStream() {
  const [steps, setSteps] = useState<AgentEvent[]>([]);
  const [summary, setSummary] = useState<AgentRunSummary | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const runIdRef = useRef<string | null>(null);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setSteps([]);
    setSummary(null);
    setError(null);
    setRunning(false);
  }, []);

  const run = useCallback(async (request: AgentRunRequest) => {
    setSteps([]);
    setSummary(null);
    setError(null);
    setRunning(true);
    const controller = new AbortController();
    abortRef.current = controller;
    runIdRef.current = null;
    try {
      await postSSE<AgentEvent>(
        '/agent/run',
        request,
        (event) => {
          runIdRef.current = event.run_id;
          if (event.event_type === 'run_end') {
            try {
              setSummary(JSON.parse(event.content) as AgentRunSummary);
            } catch {
              // A malformed summary shouldn't hide the steps.
            }
            return;
          }
          if (event.event_type === 'error') setError(event.content);
          setSteps((prev) => [...prev, event]);
        },
        controller.signal,
      );
    } catch (err) {
      if (!controller.signal.aborted) setError(getErrorMessage(err, 'The agent run failed'));
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }, []);

  const stop = useCallback(async () => {
    const runId = runIdRef.current;
    abortRef.current?.abort();
    if (runId) {
      // Best effort: the server also cancels when the stream disconnects.
      await agentApi.cancel(runId).catch(() => undefined);
    }
  }, []);

  return { steps, summary, running, error, run, stop, reset };
}
