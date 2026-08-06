import { Link, useNavigate } from 'react-router-dom';

import { projectApi, runApi } from '@/api/resources';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { RunStatusBadge } from '@/components/ui/Badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/States';
import { useAsync } from '@/hooks/useAsync';
import { useAuth } from '@/hooks/useAuth';
import { formatDuration, formatNumber, relativeTime, truncate } from '@/lib/utils';
import type { DashboardStats, Project, Run } from '@/types';

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const stats = useAsync<DashboardStats>((signal) => projectApi.stats(signal), []);
  const projects = useAsync<{ items: Project[] }>(
    (signal) => projectApi.list({ limit: 5 }, signal),
    [],
  );
  const runs = useAsync<Run[]>((signal) => runApi.list(6, signal), []);

  const firstName = user?.full_name?.split(' ')[0] ?? 'there';

  return (
    <div className="animate-fade-in">
      <PageHeader
        title={`Welcome back, ${firstName}`}
        description="Submit an idea and your AI engineering team will build it."
        actions={<Button onClick={() => navigate('/projects/new')}>New project</Button>}
      />

      <StatGrid state={stats} />

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Recent projects"
            description="Ideas you have submitted"
            action={
              <Link
                to="/projects"
                className="rounded text-xs font-medium text-brand-400 hover:text-brand-300"
              >
                View all
              </Link>
            }
          />
          {projects.isLoading ? (
            <LoadingState rows={3} />
          ) : projects.error ? (
            <ErrorState error={projects.error} onRetry={projects.reload} />
          ) : !projects.data?.items.length ? (
            <EmptyState
              title="No projects yet"
              description="Describe a software idea and the team will turn it into a project."
              action={
                <Button size="sm" onClick={() => navigate('/projects/new')}>
                  Create your first project
                </Button>
              }
            />
          ) : (
            <ul className="divide-y divide-edge">
              {projects.data.items.map((project) => (
                <li key={project.id}>
                  <Link
                    to={`/projects/${project.id}`}
                    className="flex items-center justify-between gap-4 px-5 py-3.5 transition-colors hover:bg-surface-sunken"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-content">
                        {project.name}
                      </p>
                      <p className="mt-0.5 truncate text-xs text-content-muted">
                        {truncate(project.summary ?? project.idea, 80)}
                      </p>
                    </div>
                    <span className="shrink-0 text-xs text-content-subtle">
                      {relativeTime(project.created_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader
            title="Recent generations"
            description="Runs across all your projects"
            action={
              <Link
                to="/runs"
                className="rounded text-xs font-medium text-brand-400 hover:text-brand-300"
              >
                View all
              </Link>
            }
          />
          {runs.isLoading ? (
            <LoadingState rows={3} />
          ) : runs.error ? (
            <ErrorState error={runs.error} onRetry={runs.reload} />
          ) : !runs.data?.length ? (
            <EmptyState
              title="No generations yet"
              description="Analyse a project and start a run to see it here."
            />
          ) : (
            <ul className="divide-y divide-edge">
              {runs.data.map((run) => (
                <li key={run.id}>
                  <Link
                    to={`/runs/${run.id}`}
                    className="flex items-center justify-between gap-4 px-5 py-3.5 transition-colors hover:bg-surface-sunken"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <RunStatusBadge status={run.status} />
                        <span className="truncate text-sm text-content">
                          {run.file_count > 0
                            ? `${run.file_count} files`
                            : (run.phase ?? 'queued')}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-content-subtle">
                        {relativeTime(run.created_at)} · {formatDuration(run.duration_seconds)}
                      </p>
                    </div>
                    <svg
                      className="h-4 w-4 shrink-0 text-content-subtle"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                      aria-hidden="true"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                    </svg>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function StatGrid({ state }: { state: ReturnType<typeof useAsync<DashboardStats>> }) {
  if (state.isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <div key={index} className="skeleton h-24" aria-hidden="true" />
        ))}
      </div>
    );
  }

  if (state.error) {
    return (
      <Card>
        <ErrorState error={state.error} onRetry={state.reload} />
      </Card>
    );
  }

  const stats = state.data;
  if (!stats) return null;

  const tiles = [
    { label: 'Projects', value: formatNumber(stats.total_projects) },
    {
      label: 'Generations',
      value: formatNumber(stats.total_runs),
      hint: `${stats.completed_runs} completed`,
    },
    { label: 'Files generated', value: formatNumber(stats.total_files_generated) },
    {
      label: 'Engineering time',
      value: formatDuration(stats.total_generation_seconds),
      hint: stats.active_runs > 0 ? `${stats.active_runs} running now` : undefined,
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {tiles.map((tile) => (
        <Card key={tile.label}>
          <CardBody>
            <p className="text-xs font-medium uppercase tracking-wide text-content-subtle">
              {tile.label}
            </p>
            <p className="mt-1.5 text-2xl font-semibold tabular-nums text-content">
              {tile.value}
            </p>
            {tile.hint ? (
              <p className="mt-0.5 text-xs text-content-muted">{tile.hint}</p>
            ) : null}
          </CardBody>
        </Card>
      ))}
    </div>
  );
}
