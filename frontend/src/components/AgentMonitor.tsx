import { AgentStatusBadge } from '@/components/ui/Badge';
import { Card, CardHeader } from '@/components/ui/Card';
import { BlockMeter } from '@/components/ui/Progress';
import { cn, formatDuration, percent } from '@/lib/utils';
import type { AgentExecution } from '@/types';

/** Live status of every engineer on the team. */
export function AgentMonitor({ agents }: { agents: AgentExecution[] }) {
  const completed = agents.filter((a) => a.status === 'completed').length;
  const skipped = agents.filter((a) => a.status === 'skipped').length;

  return (
    <Card>
      <CardHeader
        title="Engineering team"
        description={`${completed} completed${skipped > 0 ? `, ${skipped} skipped` : ''} of ${agents.length}`}
      />
      <ul className="divide-y divide-edge">
        {agents.map((agent) => (
          <AgentRow key={agent.role} agent={agent} />
        ))}
      </ul>
    </Card>
  );
}

const AGENT_PROVIDER_INFO: Record<string, { account: string; model: string }> = {
  manager: { account: 'PLANNER_API_KEY01 (Slot 01)', model: 'gemini-3.6-flash' },
  business_analyst: { account: 'PLANNER_API_KEY01 (Slot 01)', model: 'gemini-3.6-flash' },
  solution_architect: { account: 'PLANNER_API_KEY01 (Slot 01)', model: 'gemini-3.6-flash' },
  frontend_engineer: { account: 'FRONTEND_API_KEY01 (Slot 02)', model: 'gemini-3.6-flash' },
  documentation_engineer: { account: 'FRONTEND_API_KEY01 (Slot 02)', model: 'gemini-3.6-flash' },
  backend_engineer: { account: 'BACKEND_API_KEY01 (Slot 03)', model: 'gemini-3.6-flash' },
  database_engineer: { account: 'DATABASE_API_KEY01 (Slot 04)', model: 'gemini-3.6-flash' },
  qa_engineer: { account: 'QA_API_KEY01 (Slot 05)', model: 'gemini-3.6-flash' },
  review_engineer: { account: 'REVIEW_API_KEY01 (Slot 06)', model: 'gemini-3.6-flash' },
  improvement_engineer: { account: 'REVIEW_API_KEY01 (Slot 06)', model: 'gemini-3.6-flash' },
  final_qa: { account: 'DEBUG_API_KEY01 (Slot 07)', model: 'gemini-3.6-flash' },
  artifact_manager: { account: 'Deterministic', model: 'No LLM' },
};

function AgentRow({ agent }: { agent: AgentExecution }) {
  const isRunning = agent.status === 'running';
  const isSkipped = agent.status === 'skipped';
  const providerInfo = AGENT_PROVIDER_INFO[agent.role] ?? {
    account: 'Gemini Slot',
    model: 'gemini-3.6-flash',
  };

  const tone =
    agent.status === 'completed'
      ? 'success'
      : agent.status === 'failed'
        ? 'danger'
        : agent.status === 'skipped'
          ? 'muted'
          : 'brand';

  const meterValue =
    agent.status === 'completed' ? 100 : agent.status === 'skipped' ? 100 : agent.progress;

  return (
    <li className={cn('px-5 py-3.5 transition-colors', isRunning && 'bg-brand-500/[0.04]')}>
      <div className="flex items-center gap-3">
        <span
          className={cn(
            'h-2 w-2 shrink-0 rounded-full',
            agent.status === 'completed' && 'bg-success',
            agent.status === 'running' && 'animate-pulse-ring bg-brand-500',
            agent.status === 'failed' && 'bg-danger',
            agent.status === 'skipped' && 'bg-content-subtle',
            agent.status === 'waiting' && 'bg-edge',
          )}
          aria-hidden="true"
        />

        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p
                className={cn(
                  'truncate text-sm font-medium',
                  isSkipped ? 'text-content-subtle' : 'text-content',
                )}
              >
                {agent.display_name}
              </p>
              <p className="font-mono text-[11px] text-content-muted">
                {providerInfo.account} · {providerInfo.model}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {agent.duration_seconds ? (
                <span className="font-mono text-[11px] tabular-nums text-content-subtle">
                  {formatDuration(agent.duration_seconds)}
                </span>
              ) : null}
              <AgentStatusBadge status={agent.status} />
            </div>
          </div>

          <div className="mt-2 flex items-center gap-3">
            <BlockMeter value={meterValue} tone={tone} blocks={12} />
            {isRunning ? (
              <span className="font-mono text-[11px] tabular-nums text-content-muted">
                {agent.progress}%
              </span>
            ) : null}
            {agent.files_produced > 0 ? (
              <span className="text-[11px] text-content-subtle">
                {agent.files_produced} files
              </span>
            ) : null}
            {agent.confidence !== null && agent.status === 'completed' ? (
              <span className="text-[11px] text-content-subtle">
                {percent(agent.confidence)} confidence
              </span>
            ) : null}
          </div>

          {agent.summary && agent.status === 'completed' ? (
            <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-content-muted">
              {agent.summary}
            </p>
          ) : null}

          {agent.skip_reason && isSkipped ? (
            <p className="mt-1.5 text-xs leading-relaxed text-content-subtle">
              {agent.skip_reason}
            </p>
          ) : null}

          {agent.error_message && agent.status === 'failed' ? (
            <p className="mt-1.5 text-xs leading-relaxed text-danger">{agent.error_message}</p>
          ) : null}
        </div>
      </div>
    </li>
  );
}
