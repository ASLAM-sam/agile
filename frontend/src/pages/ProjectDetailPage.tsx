import { useCallback, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { ApiError } from '@/api/client';
import { projectApi } from '@/api/resources';
import { PageHeader } from '@/components/layout/PageHeader';
import { StackSelector } from '@/components/StackSelector';
import { WorkflowPreview } from '@/components/WorkflowPreview';
import { RunStatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { EmptyState, ErrorState, LoadingState, Spinner } from '@/components/ui/States';
import { useAsync } from '@/hooks/useAsync';
import { formatDuration, relativeTime, titleCase } from '@/lib/utils';
import type { AnalysisResult, Project, Run, TechStack } from '@/types';

export function ProjectDetailPage() {
  const { projectId = '' } = useParams();
  const navigate = useNavigate();

  const project = useAsync<Project>((signal) => projectApi.get(projectId, signal), [projectId]);
  const runs = useAsync<Run[]>((signal) => projectApi.runs(projectId, signal), [projectId]);

  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [isAnalysing, setAnalysing] = useState(false);
  const [analysisError, setAnalysisError] = useState<ApiError | null>(null);
  const [selectedStack, setSelectedStack] = useState<Partial<TechStack>>({});
  const [isStarting, setStarting] = useState(false);
  const [startError, setStartError] = useState<ApiError | null>(null);

  const runAnalysis = useCallback(async () => {
    setAnalysing(true);
    setAnalysisError(null);
    try {
      const result = await projectApi.analyse(projectId);
      setAnalysis(result);
      setSelectedStack({
        frontend: result.recommended_stack.frontend,
        backend: result.recommended_stack.backend,
        database: result.recommended_stack.database,
      });
    } catch (caught) {
      setAnalysisError(
        caught instanceof ApiError
          ? caught
          : new ApiError(0, 'unexpected', 'Analysis failed. Please try again.'),
      );
    } finally {
      setAnalysing(false);
    }
  }, [projectId]);

  async function startGeneration() {
    setStarting(true);
    setStartError(null);
    try {
      const run = await projectApi.startRun(projectId, selectedStack);
      navigate(`/runs/${run.id}`);
    } catch (caught) {
      setStartError(
        caught instanceof ApiError
          ? caught
          : new ApiError(0, 'unexpected', 'The run could not be started.'),
      );
      setStarting(false);
    }
  }

  if (project.isLoading) return <LoadingState rows={5} label="Loading project…" />;
  if (project.error) return <ErrorState error={project.error} onRetry={project.reload} />;
  if (!project.data) return null;

  const data = project.data;

  return (
    <div className="animate-fade-in">
      <PageHeader
        title={data.name}
        description={data.summary ?? data.idea}
        breadcrumbs={[{ label: 'Projects', to: '/projects' }, { label: data.name }]}
        actions={
          analysis ? (
            <Button onClick={startGeneration} isLoading={isStarting}>
              Start generation
            </Button>
          ) : (
            <Button onClick={runAnalysis} isLoading={isAnalysing}>
              Analyse requirements
            </Button>
          )
        }
      />

      {startError ? (
        <div className="mb-5">
          <Card>
            <ErrorState error={startError} onRetry={startGeneration} />
          </Card>
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {!analysis && !isAnalysing && !analysisError ? (
            <Card>
              <EmptyState
                title="Ready to analyse"
                description="The Business Analyst will read your idea, write the requirements and decide which capabilities this project actually needs — authentication, a database, an API, or none of them."
                action={
                  <Button onClick={runAnalysis} isLoading={isAnalysing}>
                    Analyse requirements
                  </Button>
                }
              />
            </Card>
          ) : null}

          {isAnalysing ? (
            <Card>
              <CardBody className="flex flex-col items-center gap-3 py-14 text-center">
                <Spinner className="h-7 w-7" />
                <p className="text-sm font-medium text-content">
                  The Business Analyst is reading your idea
                </p>
                <p className="max-w-sm text-xs text-content-muted">
                  Writing requirements, identifying actors and entities, and deciding
                  which capabilities the project needs. This usually takes under a minute.
                </p>
              </CardBody>
            </Card>
          ) : null}

          {analysisError ? (
            <Card>
              <ErrorState error={analysisError} onRetry={runAnalysis} />
            </Card>
          ) : null}

          {analysis ? <AnalysisPanel analysis={analysis} /> : null}
        </div>

        <div className="space-y-6">
          {analysis ? (
            <>
              <StackSelector
                options={analysis.options}
                recommended={analysis.recommended_stack}
                capabilities={analysis.analysis.capabilities}
                value={selectedStack}
                onChange={setSelectedStack}
              />
              <WorkflowPreview steps={analysis.workflow_preview} />
            </>
          ) : null}

          <Card>
            <CardHeader title="Generation history" />
            {runs.isLoading ? (
              <LoadingState rows={2} />
            ) : runs.error ? (
              <ErrorState error={runs.error} onRetry={runs.reload} />
            ) : !runs.data?.length ? (
              <CardBody>
                <p className="text-xs text-content-muted">
                  No runs yet. Analyse the project, then start generation.
                </p>
              </CardBody>
            ) : (
              <ul className="divide-y divide-edge">
                {runs.data.map((run) => (
                  <li key={run.id}>
                    <Link
                      to={`/runs/${run.id}`}
                      className="block px-5 py-3 transition-colors hover:bg-surface-sunken"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <RunStatusBadge status={run.status} />
                        <span className="text-xs text-content-subtle">
                          {relativeTime(run.created_at)}
                        </span>
                      </div>
                      <p className="mt-1.5 text-xs text-content-muted">
                        {run.file_count} files · {formatDuration(run.duration_seconds)}
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function AnalysisPanel({ analysis }: { analysis: AnalysisResult }) {
  const a = analysis.analysis;
  const capabilities = [
    { key: 'needs_authentication', label: 'Authentication' },
    { key: 'needs_database', label: 'Database' },
    { key: 'needs_api', label: 'API' },
    { key: 'needs_backend', label: 'Backend' },
    { key: 'needs_frontend', label: 'Frontend' },
  ] as const;

  return (
    <>
      <Card>
        <CardHeader
          title="Requirement analysis"
          description={`${titleCase(a.complexity)} complexity`}
        />
        <CardBody className="space-y-5">
          <p className="text-sm leading-relaxed text-content">{a.executive_summary}</p>

          <div>
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-content-subtle">
              Capabilities required
            </h4>
            <div className="flex flex-wrap gap-2">
              {capabilities.map(({ key, label }) => {
                const enabled = a.capabilities[key];
                return (
                  <span
                    key={key}
                    className={
                      enabled
                        ? 'inline-flex items-center gap-1.5 rounded-full border border-success/25 bg-success/10 px-2.5 py-0.5 text-xs font-medium text-success'
                        : 'inline-flex items-center gap-1.5 rounded-full border border-edge px-2.5 py-0.5 text-xs font-medium text-content-subtle line-through'
                    }
                  >
                    {label}
                  </span>
                );
              })}
            </div>
            {a.rationale ? (
              <p className="mt-3 text-xs leading-relaxed text-content-muted">{a.rationale}</p>
            ) : null}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Metric label="Functional requirements" value={a.functional_requirements.length} />
            <Metric label="Non-functional" value={a.non_functional_requirements.length} />
            <Metric label="User stories" value={a.user_stories.length} />
            <Metric label="Use cases" value={a.use_cases.length} />
          </div>

          {a.entities.length > 0 ? (
            <div>
              <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-content-subtle">
                Domain entities
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {a.entities.map((entity) => (
                  <span
                    key={entity}
                    className="rounded-md bg-surface-sunken px-2 py-0.5 font-mono text-xs text-content-muted"
                  >
                    {entity}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </CardBody>
      </Card>

      {a.functional_requirements.length > 0 ? (
        <Card>
          <CardHeader
            title="Functional requirements"
            description={`${a.functional_requirements.length} requirements across ${
              new Set(a.functional_requirements.map((r) => r.module)).size
            } modules`}
          />
          <div className="max-h-96 overflow-y-auto">
            <ul className="divide-y divide-edge">
              {a.functional_requirements.map((requirement) => (
                <li key={requirement.id} className="px-5 py-3">
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 shrink-0 font-mono text-xs text-content-subtle">
                      {requirement.id}
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-content">{requirement.title}</p>
                      <p className="mt-0.5 text-xs leading-relaxed text-content-muted">
                        {requirement.description}
                      </p>
                      <div className="mt-1.5 flex gap-2 text-[11px] text-content-subtle">
                        <span className="uppercase">{requirement.priority}</span>
                        <span>·</span>
                        <span>{requirement.module}</span>
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </Card>
      ) : null}

      {a.assumptions.length > 0 ? (
        <Card>
          <CardHeader title="Assumptions" description="Choices made where the idea was ambiguous" />
          <CardBody>
            <ul className="space-y-2">
              {a.assumptions.map((assumption) => (
                <li key={assumption} className="flex gap-2 text-xs text-content-muted">
                  <span className="text-content-subtle" aria-hidden="true">
                    •
                  </span>
                  {assumption}
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-surface-sunken px-3 py-2.5">
      <p className="text-lg font-semibold tabular-nums text-content">{value}</p>
      <p className="text-xs text-content-muted">{label}</p>
    </div>
  );
}
