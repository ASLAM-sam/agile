import { Link, useNavigate } from 'react-router-dom';

import { runApi } from '@/api/resources';
import { PageHeader } from '@/components/layout/PageHeader';
import { RunStatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/States';
import { useAsync } from '@/hooks/useAsync';
import { formatDuration, formatNumber, relativeTime } from '@/lib/utils';
import type { Run } from '@/types';

export function RunsPage() {
  const navigate = useNavigate();
  const state = useAsync<Run[]>((signal) => runApi.list(50, signal), []);

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Generations"
        description="Every generation run across your projects"
        actions={
          <Button variant="secondary" onClick={state.reload} isLoading={state.isRefreshing}>
            Refresh
          </Button>
        }
      />

      {state.isLoading ? (
        <LoadingState rows={6} label="Loading generation runs…" />
      ) : state.error ? (
        <Card>
          <ErrorState error={state.error} onRetry={state.reload} />
        </Card>
      ) : !state.data?.length ? (
        <Card>
          <EmptyState
            title="No generations yet"
            description="Create a project, analyse it, then start a run to see it here."
            action={
              <Button size="sm" onClick={() => navigate('/projects/new')}>
                New project
              </Button>
            }
          />
        </Card>
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-edge text-xs uppercase tracking-wide text-content-subtle">
                  <th scope="col" className="px-5 py-3 font-medium">Status</th>
                  <th scope="col" className="px-5 py-3 font-medium">Phase</th>
                  <th scope="col" className="px-5 py-3 text-right font-medium">Files</th>
                  <th scope="col" className="px-5 py-3 text-right font-medium">Duration</th>
                  <th scope="col" className="px-5 py-3 text-right font-medium">Started</th>
                  <th scope="col" className="px-5 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {state.data.map((run) => (
                  <tr key={run.id} className="transition-colors hover:bg-surface-sunken">
                    <td className="px-5 py-3">
                      <RunStatusBadge status={run.status} />
                    </td>
                    <td className="px-5 py-3 text-xs text-content-muted">
                      {run.phase ?? '—'}
                    </td>
                    <td className="px-5 py-3 text-right font-mono text-xs tabular-nums text-content-muted">
                      {run.file_count > 0 ? formatNumber(run.file_count) : '—'}
                    </td>
                    <td className="px-5 py-3 text-right font-mono text-xs tabular-nums text-content-muted">
                      {formatDuration(run.duration_seconds)}
                    </td>
                    <td className="px-5 py-3 text-right text-xs text-content-subtle">
                      {relativeTime(run.created_at)}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <Link
                        to={`/runs/${run.id}`}
                        className="rounded text-xs font-medium text-brand-400 hover:text-brand-300"
                      >
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
