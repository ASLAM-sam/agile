import { useState } from 'react';
import { useParams } from 'react-router-dom';

import { ApiError, downloadFile } from '@/api/client';
import { runApi } from '@/api/resources';
import { AgentMonitor } from '@/components/AgentMonitor';
import { GenerationConsole } from '@/components/GenerationConsole';
import { GenerationReportView } from '@/components/GenerationReport';
import { GenerationResult } from '@/components/GenerationResult';
import { PageHeader } from '@/components/layout/PageHeader';
import { RunStatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { ProgressBar } from '@/components/ui/Progress';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/States';
import { useAsync } from '@/hooks/useAsync';
import { useRunStream } from '@/hooks/useRunStream';
import { cn, formatBytes, formatDuration, formatNumber } from '@/lib/utils';
import type { WorkspaceFile } from '@/types';

type Tab = 'monitor' | 'report' | 'files';

export function RunDetailPage() {
  const { runId = '' } = useParams();
  const { run, events, agents, isConnected, isFinished, error, reload } = useRunStream(runId);
  const [tab, setTab] = useState<Tab>('monitor');
  const [isDownloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function handleDownload() {
    setDownloading(true);
    setDownloadError(null);
    try {
      const isPartial = run?.status === 'failed' || run?.artifact?.type === 'partial' || run?.artifact_type === 'partial';
      const fallbackName = run?.artifact?.name ?? run?.artifact_name ?? (isPartial ? 'project-partial.zip' : `${run?.project_name ?? 'project'}.zip`);
      const downloadPath = run?.artifact?.download_url ?? run?.download_url ?? `/runs/${runId}/download`;
      await runApi.download(runId, fallbackName, downloadPath);
    } catch (caught) {
      setDownloadError(
        caught instanceof ApiError ? caught.message : 'The download could not be completed.',
      );
    } finally {
      setDownloading(false);
    }
  }

  async function handleCancel() {
    try {
      await runApi.cancel(runId);
      reload();
    } catch {
      // The run reached a terminal state first; the refreshed view will show it.
      reload();
    }
  }

  if (error && !run) {
    return (
      <Card>
        <ErrorState error={error} onRetry={reload} />
      </Card>
    );
  }

  if (!run) return <LoadingState rows={5} label="Loading run…" />;

  const isPackaging = run.status === 'packaging' || run.phase === 'packaging';
  const isActive = !isFinished && !isPackaging;
  const completedAgents = agents.filter(
    (a) => a.status === 'completed' || a.status === 'skipped' || a.status === 'failed',
  ).length;
  const overallProgress =
    agents.length > 0 ? (completedAgents / agents.length) * 100 : run.progress;
  const hasPartialArtifact =
    run.status === 'failed' && Boolean(
      run.artifact?.available ??
      run.artifact_available ??
      (run.file_count && run.file_count > 0) ??
      ((run.artifact_count ?? 0) > 0)
    );

  const tabs: Array<{ id: Tab; label: string; disabled?: boolean }> = [
    { id: 'monitor', label: 'Live monitor' },
    { id: 'report', label: 'Report', disabled: !run.report },
    { id: 'files', label: `Files${run.file_count ? ` (${run.file_count})` : ''}`, disabled: run.file_count === 0 },
  ];

  return (
    <div className="animate-fade-in">
      <PageHeader
        title={run.project_name ?? 'Generation run'}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <RunStatusBadge status={run.status} />
            {run.duration_seconds ? (
              <span>{formatDuration(run.duration_seconds)}</span>
            ) : null}
            {run.file_count > 0 ? <span>· {run.file_count} files</span> : null}
          </span>
        }
        breadcrumbs={[
          { label: 'Generations', to: '/runs' },
          { label: run.project_name ?? 'Run' },
        ]}
        actions={
          <>
            {isPackaging ? (
              <span className="flex items-center gap-2 text-sm font-medium text-amber-300 animate-pulse">
                Preparing artifact…
              </span>
            ) : null}
            {isActive ? (
              <Button variant="secondary" onClick={handleCancel}>
                Cancel
              </Button>
            ) : null}
            {run.status === 'completed' ? (
              <Button onClick={handleDownload} isLoading={isDownloading}>
                Download ZIP
              </Button>
            ) : null}
            {hasPartialArtifact ? (
              <Button
                variant="secondary"
                onClick={handleDownload}
                isLoading={isDownloading}
                className="border-amber-500/40 text-amber-200 hover:bg-amber-800/30"
              >
                Download Partial ZIP
              </Button>
            ) : null}
          </>
        }
      />

      {downloadError ? (
        <div
          className="mb-5 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger"
          role="alert"
        >
          {downloadError}
        </div>
      ) : null}

      {run.status === 'failed' ? (
        <GenerationResult
          run={run}
          onDownload={handleDownload}
          isDownloading={isDownloading}
        />
      ) : null}

      {isActive ? (
        <Card className="mb-5">
          <CardBody>
            <ProgressBar
              value={overallProgress}
              label={`${completedAgents} of ${agents.length} agents finished`}
              showValue
              animated={isConnected}
            />
          </CardBody>
        </Card>
      ) : null}

      <div className="mb-5 flex gap-1 border-b border-edge" role="tablist">
        {tabs.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            aria-selected={tab === entry.id}
            disabled={entry.disabled}
            onClick={() => setTab(entry.id)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
              'disabled:cursor-not-allowed disabled:opacity-40',
              tab === entry.id
                ? 'border-brand-500 text-content'
                : 'border-transparent text-content-muted hover:text-content',
            )}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {tab === 'monitor' ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <AgentMonitor agents={agents} />
          <GenerationConsole
            events={events}
            isConnected={isConnected}
            isFinished={isFinished}
          />
        </div>
      ) : null}

      {tab === 'report' && run.report ? <GenerationReportView report={run.report} /> : null}

      {tab === 'files' ? <FileExplorer runId={runId} /> : null}
    </div>
  );
}

function FileExplorer({ runId }: { runId: string }) {
  const state = useAsync<WorkspaceFile[]>((signal) => runApi.files(runId, signal), [runId]);

  if (state.isLoading) return <LoadingState rows={6} label="Loading file manifest…" />;
  if (state.error) {
    return (
      <Card>
        <ErrorState error={state.error} onRetry={state.reload} />
      </Card>
    );
  }
  if (!state.data?.length) {
    return (
      <Card>
        <EmptyState
          title="No files recorded"
          description="This run did not produce a file manifest."
        />
      </Card>
    );
  }

  const files = state.data;
  const totalBytes = files.reduce((sum, file) => sum + file.size_bytes, 0);
  const totalLines = files.reduce((sum, file) => sum + file.line_count, 0);

  // Group by top-level directory so the structure is legible at a glance.
  const grouped = files.reduce<Record<string, WorkspaceFile[]>>((accumulator, file) => {
    const segments = file.path.split('/');
    const root = segments.length > 1 ? (segments[0] ?? 'root') : 'root';
    (accumulator[root] ??= []).push(file);
    return accumulator;
  }, {});

  return (
    <Card>
      <CardHeader
        title="Generated files"
        description={`${files.length} files · ${formatNumber(totalLines)} lines · ${formatBytes(totalBytes)}`}
      />
      <div className="max-h-[640px] overflow-y-auto">
        {Object.entries(grouped)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([directory, entries]) => (
            <section key={directory}>
              <h3 className="sticky top-0 z-10 border-b border-edge bg-surface-raised px-5 py-2 font-mono text-xs font-semibold text-content-muted">
                {directory}/ <span className="font-normal">({entries.length})</span>
              </h3>
              <ul className="divide-y divide-edge">
                {entries.map((file) => (
                  <li
                    key={file.path}
                    className="flex items-center justify-between gap-4 px-5 py-2.5"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-mono text-xs text-content">{file.path}</p>
                      {file.description ? (
                        <p className="mt-0.5 truncate text-xs text-content-muted">
                          {file.description}
                        </p>
                      ) : null}
                    </div>
                    <span className="shrink-0 font-mono text-[11px] tabular-nums text-content-subtle">
                      {file.line_count} L · {formatBytes(file.size_bytes)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
      </div>
    </Card>
  );
}
