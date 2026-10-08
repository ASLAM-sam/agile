/**
 * Live run subscription.
 *
 * Opens the SSE stream, folds incoming events into agent state, and reconnects
 * with backoff if the connection drops mid-run. The stream replays history
 * from the last sequence seen, so a reconnect leaves no gap in the timeline.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, streamEvents } from '@/api/client';
import { runApi } from '@/api/resources';
import type { AgentExecution, Run, RunEvent } from '@/types';

const MAX_EVENTS = 600;
const MAX_RECONNECT_ATTEMPTS = 5;

export interface RunStreamState {
  run: Run | null;
  events: RunEvent[];
  agents: AgentExecution[];
  isConnected: boolean;
  isFinished: boolean;
  error: ApiError | null;
  reload: () => void;
}

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled']);

export function useRunStream(runId: string | undefined): RunStreamState {
  const [run, setRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [agents, setAgents] = useState<AgentExecution[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [nonce, setNonce] = useState(0);

  const lastSequence = useRef(0);
  const isFinished = run !== null && TERMINAL_STATUSES.has(run.status);

  const reload = useCallback(() => {
    lastSequence.current = 0;
    setEvents([]);
    setNonce((value) => value + 1);
  }, []);

  // Load the run snapshot: agent roster, plan and current status.
  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();

    runApi
      .get(runId, controller.signal)
      .then((result) => {
        setRun(result);
        setAgents(result.agents ?? []);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        if (caught instanceof ApiError) setError(caught);
      });

    return () => controller.abort();
  }, [runId, nonce]);

  // Subscribe to the event stream.
  useEffect(() => {
    if (!runId) return;

    const controller = new AbortController();
    let attempt = 0;
    let stopped = false;
    let retryTimer: number | undefined;

    async function consume(): Promise<void> {
      try {
        setIsConnected(true);
        const path = `/runs/${runId}/stream?after=${lastSequence.current}`;

        for await (const frame of streamEvents(path, controller.signal)) {
          if (stopped) return;

          if (frame.event === 'stream.end') {
            stopped = true;
            setIsConnected(false);
            // Fetch the final snapshot so totals and the report are current.
            if (runId) {
              runApi
                .get(runId)
                .then((result) => {
                  setRun(result);
                  setAgents(result.agents ?? []);
                })
                .catch(() => {
                  /* the timeline already reflects the outcome */
                });
            }
            return;
          }

          let event: RunEvent;
          try {
            event = JSON.parse(frame.data) as RunEvent;
          } catch {
            continue; // a malformed frame must not kill the stream
          }

          attempt = 0; // a delivered event proves the connection is healthy
          if (event.sequence <= lastSequence.current) continue;
          lastSequence.current = event.sequence;

          setEvents((current) => {
            const next = [...current, event];
            return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next;
          });

          applyEvent(event, setAgents, setRun);

          if (
            event.type === 'artifact.created' ||
            event.type === 'run.completed' ||
            event.type === 'run.failed'
          ) {
            runApi
              .get(runId)
              .then((result) => {
                setRun(result);
                setAgents(result.agents ?? []);
              })
              .catch(() => {});
          }
        }

        // The generator completed without a stream.end frame: the server
        // closed the connection. Reconnect unless we are done.
        if (!stopped) scheduleRetry();
      } catch (caught: unknown) {
        if (stopped || controller.signal.aborted) return;
        if (caught instanceof DOMException && caught.name === 'AbortError') return;

        setIsConnected(false);
        if (caught instanceof ApiError && !caught.isRetryable) {
          setError(caught);
          return;
        }
        scheduleRetry();
      }
    }

    function scheduleRetry(): void {
      if (stopped || attempt >= MAX_RECONNECT_ATTEMPTS) {
        setIsConnected(false);
        if (attempt >= MAX_RECONNECT_ATTEMPTS) {
          setError(
            new ApiError(
              0,
              'stream_lost',
              'Lost connection to the live stream. Reload to catch up.',
            ),
          );
        }
        return;
      }
      const delay = Math.min(1000 * 2 ** attempt, 15000);
      attempt += 1;
      retryTimer = window.setTimeout(() => void consume(), delay);
    }

    void consume();

    return () => {
      stopped = true;
      controller.abort();
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      setIsConnected(false);
    };
  }, [runId, nonce]);

  return { run, events, agents, isConnected, isFinished, error, reload };
}

/** Fold one event into agent and run state. */
function applyEvent(
  event: RunEvent,
  setAgents: React.Dispatch<React.SetStateAction<AgentExecution[]>>,
  setRun: React.Dispatch<React.SetStateAction<Run | null>>,
): void {
  if (event.agent) {
    setAgents((current) =>
      current.map((agent) => {
        if (agent.role !== event.agent) return agent;

        switch (event.type) {
          case 'agent.started':
            return { ...agent, status: 'running', progress: 0 };
          case 'agent.progress': {
            const progress = Number(event.payload?.['progress'] ?? agent.progress);
            return { ...agent, status: 'running', progress };
          }
          case 'agent.completed':
            return {
              ...agent,
              status: 'completed',
              progress: 100,
              summary: event.message,
              files_produced: Number(event.payload?.['files_produced'] ?? agent.files_produced),
              duration_seconds: Number(
                event.payload?.['duration_seconds'] ?? agent.duration_seconds ?? 0,
              ),
            };
          case 'agent.skipped':
            return { ...agent, status: 'skipped', skip_reason: event.message };
          case 'agent.failed':
            return { ...agent, status: 'failed', error_message: event.message };
          default:
            return agent;
        }
      }),
    );
  }

  if (event.type === 'run.completed' || event.type === 'run.failed' || event.type === 'run.cancelled') {
    const status =
      event.type === 'run.completed'
        ? 'completed'
        : event.type === 'run.failed'
          ? 'failed'
          : 'cancelled';
    setRun((current) => (current ? { ...current, status, progress: 100 } : current));
  }
}
