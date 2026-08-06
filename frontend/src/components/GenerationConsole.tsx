import { useEffect, useRef, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Card, CardHeader } from '@/components/ui/Card';
import { cn, formatTime, titleCase } from '@/lib/utils';
import type { RunEvent } from '@/types';

const LEVEL_STYLES: Record<string, string> = {
  debug: 'text-content-subtle',
  info: 'text-content-muted',
  warning: 'text-warning',
  error: 'text-danger',
};

/**
 * Live generation console.
 *
 * Auto-scrolls while the user is at the bottom, and stops the moment they
 * scroll up to read something — yanking the viewport away mid-read is the
 * fastest way to make a live log useless.
 */
export function GenerationConsole({
  events,
  isConnected,
  isFinished,
}: {
  events: RunEvent[];
  isConnected: boolean;
  isFinished: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [isPinned, setPinned] = useState(true);

  useEffect(() => {
    if (!isPinned) return;
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [events, isPinned]);

  function handleScroll() {
    const element = scrollRef.current;
    if (!element) return;
    const distanceFromBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    setPinned(distanceFromBottom < 40);
  }

  return (
    <Card className="flex h-[520px] flex-col overflow-hidden">
      <CardHeader
        title="Generation console"
        description={`${events.length} events`}
        action={
          isFinished ? (
            <Badge tone="muted">Stream closed</Badge>
          ) : isConnected ? (
            <Badge tone="success" dot>
              Live
            </Badge>
          ) : (
            <Badge tone="warning" dot>
              Reconnecting
            </Badge>
          )
        }
      />

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto bg-surface-sunken/50 px-4 py-3 font-mono text-xs"
        role="log"
        aria-live="polite"
        aria-label="Generation event log"
      >
        {events.length === 0 ? (
          <p className="py-8 text-center text-content-subtle">
            Waiting for the first event…
          </p>
        ) : (
          <ol className="space-y-1">
            {events.map((event) => (
              <li
                key={event.sequence}
                className="flex animate-slide-in gap-2.5 leading-relaxed"
              >
                <span className="shrink-0 tabular-nums text-content-subtle">
                  {formatTime(event.timestamp)}
                </span>
                {event.agent ? (
                  <span className="w-[9.5rem] shrink-0 truncate text-brand-400">
                    {titleCase(event.agent)}
                  </span>
                ) : (
                  <span className="w-[9.5rem] shrink-0 text-content-subtle">system</span>
                )}
                <span className={cn('min-w-0 flex-1 break-words', LEVEL_STYLES[event.level])}>
                  {event.message}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>

      {!isPinned ? (
        <button
          type="button"
          onClick={() => {
            setPinned(true);
            const element = scrollRef.current;
            if (element) element.scrollTop = element.scrollHeight;
          }}
          className="border-t border-edge bg-surface-raised py-2 text-xs font-medium text-brand-400 hover:bg-surface-sunken"
        >
          Jump to latest
        </button>
      ) : null}
    </Card>
  );
}
