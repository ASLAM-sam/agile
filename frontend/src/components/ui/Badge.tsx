import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';
import type { AgentStatus, RunStatus } from '@/types';

export type BadgeTone = 'neutral' | 'brand' | 'success' | 'warning' | 'danger' | 'muted';

const TONES: Record<BadgeTone, string> = {
  neutral: 'bg-surface-sunken text-content-muted border-edge',
  brand: 'bg-brand-500/10 text-brand-400 border-brand-500/25',
  success: 'bg-success/10 text-success border-success/25',
  warning: 'bg-warning/10 text-warning border-warning/25',
  danger: 'bg-danger/10 text-danger border-danger/25',
  muted: 'bg-transparent text-content-subtle border-edge',
};

export function Badge({
  tone = 'neutral',
  children,
  className,
  dot = false,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5',
        'text-xs font-medium leading-5',
        TONES[tone],
        className,
      )}
    >
      {dot ? (
        <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      ) : null}
      {children}
    </span>
  );
}

const RUN_TONES: Record<RunStatus, BadgeTone> = {
  pending: 'neutral',
  analyzing: 'brand',
  awaiting_review: 'warning',
  running: 'brand',
  packaging: 'brand',
  completed: 'success',
  failed: 'danger',
  cancelled: 'muted',
};

const RUN_LABELS: Record<RunStatus, string> = {
  pending: 'Queued',
  analyzing: 'Analysing',
  awaiting_review: 'Awaiting review',
  running: 'Running',
  packaging: 'Packaging',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const isActive = status === 'running' || status === 'analyzing' || status === 'packaging';
  return (
    <Badge tone={RUN_TONES[status]} dot={isActive}>
      {RUN_LABELS[status]}
    </Badge>
  );
}

const AGENT_TONES: Record<AgentStatus, BadgeTone> = {
  waiting: 'muted',
  running: 'brand',
  completed: 'success',
  skipped: 'neutral',
  failed: 'danger',
};

const AGENT_LABELS: Record<AgentStatus, string> = {
  waiting: 'Waiting',
  running: 'Running',
  completed: 'Done',
  skipped: 'Skipped',
  failed: 'Failed',
};

export function AgentStatusBadge({ status }: { status: AgentStatus }) {
  return (
    <Badge tone={AGENT_TONES[status]} dot={status === 'running'}>
      {AGENT_LABELS[status]}
    </Badge>
  );
}
