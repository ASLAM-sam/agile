import { catalogApi } from '@/api/resources';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useAsync } from '@/hooks/useAsync';
import { titleCase } from '@/lib/utils';
import type { AdapterDescriptor, Catalogue } from '@/types';

export function TeamPage() {
  const state = useAsync<Catalogue>((signal) => catalogApi.get(signal), []);

  if (state.isLoading) return <LoadingState rows={6} label="Loading the team roster…" />;
  if (state.error) {
    return (
      <Card>
        <ErrorState error={state.error} onRetry={state.reload} />
      </Card>
    );
  }
  if (!state.data) return null;

  const { agents, frontend, backend, database } = state.data;

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="AI engineering team"
        description="Eleven specialised agents. Only the ones a project needs are engaged."
      />

      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map((agent, index) => (
          <Card key={agent.role} className="flex h-full flex-col p-5">
            <div className="mb-3 flex items-center gap-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-500/15 font-mono text-xs font-semibold text-brand-400">
                {String(index + 1).padStart(2, '0')}
              </span>
              <h2 className="text-sm font-semibold text-content">{agent.display_name}</h2>
            </div>
            <p className="flex-1 text-xs leading-relaxed text-content-muted">
              {agent.description}
            </p>
            {agent.depends_on ? (
              <p className="mt-3 border-t border-edge pt-3 text-[11px] text-content-subtle">
                Runs after: {agent.depends_on.split(', ').map(titleCase).join(', ')}
              </p>
            ) : (
              <p className="mt-3 border-t border-edge pt-3 text-[11px] text-content-subtle">
                Runs first
              </p>
            )}
          </Card>
        ))}
      </div>

      <PageHeader
        title="Supported technologies"
        description="Adapters register themselves; adding one requires no change to the workflow."
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <AdapterGroup title="Frontend" adapters={frontend} />
        <AdapterGroup title="Backend" adapters={backend} />
        <AdapterGroup title="Database" adapters={database} />
      </div>
    </div>
  );
}

function AdapterGroup({ title, adapters }: { title: string; adapters: AdapterDescriptor[] }) {
  return (
    <Card>
      <CardHeader title={title} description={`${adapters.length} adapters`} />
      <CardBody className="space-y-4">
        {adapters.map((adapter) => (
          <div key={adapter.key} className="border-b border-edge pb-4 last:border-0 last:pb-0">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-medium text-content">{adapter.display_name}</h3>
              <Badge tone="muted">{adapter.version}</Badge>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-content-muted">
              {adapter.description}
            </p>
            {adapter.best_for.length > 0 ? (
              <ul className="mt-2 space-y-0.5">
                {adapter.best_for.map((item) => (
                  <li key={item} className="text-[11px] text-content-subtle">
                    • {item}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ))}
      </CardBody>
    </Card>
  );
}
