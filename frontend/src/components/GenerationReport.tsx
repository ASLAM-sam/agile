import { Badge } from '@/components/ui/Badge';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { ProgressBar } from '@/components/ui/Progress';
import { cn, formatBytes, formatNumber, percent, titleCase } from '@/lib/utils';
import type { GenerationReport } from '@/types';

/** The AI Engineering Report, as shown in the dashboard. */
export function GenerationReportView({ report }: { report: GenerationReport }) {
  const delivered = report.artifacts.filter((artifact) => artifact.delivered).length;

  return (
    <div className="space-y-6">
      <Card>
        <CardBody className="space-y-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 className="text-lg font-semibold text-content">{report.project.name}</h2>
              <p className="mt-1 max-w-2xl text-sm leading-relaxed text-content-muted">
                {report.project.summary || report.project.idea}
              </p>
            </div>
            <Badge tone={report.status === 'Ready for development' ? 'success' : 'warning'}>
              {report.status}
            </Badge>
          </div>

          {report.status_detail ? (
            <p className="text-xs text-content-muted">{report.status_detail}</p>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Generation time" value={report.timing.duration_display} />
            <Metric
              label="Files generated"
              value={formatNumber(report.statistics.file_count)}
              hint={`${formatNumber(report.statistics.total_lines)} lines`}
            />
            <Metric
              label="Agents executed"
              value={`${report.agents.executed} / ${report.agents.total}`}
              hint={report.agents.skipped > 0 ? `${report.agents.skipped} skipped` : undefined}
            />
            <Metric
              label="Package size"
              value={formatBytes(report.statistics.total_bytes)}
            />
          </div>
        </CardBody>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Estimated manual development effort"
            description="Derived from the delivered artefacts, not asserted"
          />
          <CardBody className="space-y-4">
            <p className="text-3xl font-semibold text-brand-400">
              {report.effort_saved.display}
            </p>
            <ul className="space-y-1.5">
              {report.effort_saved.basis.map((item) => (
                <li key={item} className="flex gap-2 text-xs text-content-muted">
                  <span className="text-content-subtle" aria-hidden="true">
                    •
                  </span>
                  {item}
                </li>
              ))}
            </ul>
            <p className="border-t border-edge pt-3 text-xs text-content-subtle">
              {report.effort_saved.hours_low}–{report.effort_saved.hours_high} developer-hours,
              using a ±35% band for team speed and domain familiarity.
            </p>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="AI confidence"
            description="Self-reported completeness per dimension"
          />
          <CardBody className="space-y-3.5">
            {Object.entries(report.confidence.dimensions)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([dimension, score]) => (
                <ProgressBar
                  key={dimension}
                  value={score * 100}
                  label={titleCase(dimension)}
                  showValue
                  tone={score >= 0.8 ? 'success' : score >= 0.6 ? 'brand' : 'danger'}
                  size="sm"
                />
              ))}
            <div className="border-t border-edge pt-3">
              <ProgressBar
                value={report.confidence.overall * 100}
                label="Overall"
                showValue
                tone="brand"
              />
            </div>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Engineering team"
          description={`${report.agents.executed} executed, ${report.agents.skipped} skipped, ${report.agents.failed} failed`}
        />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-edge text-xs uppercase tracking-wide text-content-subtle">
                <th scope="col" className="px-5 py-2.5 font-medium">Agent</th>
                <th scope="col" className="px-5 py-2.5 font-medium">Status</th>
                <th scope="col" className="px-5 py-2.5 font-medium">Outcome</th>
                <th scope="col" className="px-5 py-2.5 text-right font-medium">Files</th>
                <th scope="col" className="px-5 py-2.5 text-right font-medium">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {report.agents.detail.map((agent) => (
                <tr key={agent.role}>
                  <td className="px-5 py-2.5 font-medium text-content">
                    {agent.display_name}
                  </td>
                  <td className="px-5 py-2.5">
                    <span
                      className={cn(
                        'text-xs font-medium',
                        agent.status === 'completed' && 'text-success',
                        agent.status === 'skipped' && 'text-content-subtle',
                        agent.status === 'failed' && 'text-danger',
                      )}
                    >
                      {titleCase(agent.status)}
                    </span>
                  </td>
                  <td className="max-w-md px-5 py-2.5 text-xs text-content-muted">
                    {agent.summary}
                  </td>
                  <td className="px-5 py-2.5 text-right font-mono text-xs tabular-nums text-content-muted">
                    {agent.files_produced || '—'}
                  </td>
                  <td className="px-5 py-2.5 text-right font-mono text-xs tabular-nums text-content-muted">
                    {agent.duration_seconds.toFixed(1)}s
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Artifacts delivered"
            description={`${delivered} of ${report.artifacts.length}`}
          />
          <CardBody>
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {report.artifacts.map((artifact) => (
                <li key={artifact.name} className="flex items-start gap-2 text-xs">
                  <span
                    className={cn(
                      'mt-0.5 shrink-0',
                      artifact.delivered ? 'text-success' : 'text-content-subtle',
                    )}
                    aria-hidden="true"
                  >
                    {artifact.delivered ? '✓' : '○'}
                  </span>
                  <span className={artifact.delivered ? 'text-content' : 'text-content-subtle'}>
                    {artifact.name}
                    {artifact.detail ? (
                      <span className="text-content-subtle"> — {artifact.detail}</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Quality verification" />
          <CardBody className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Metric label="Review score" value={percent(report.quality.review_score)} />
              <Metric
                label="Issues found"
                value={String(report.quality.issues_found)}
                hint={`${report.quality.blocking_issues} blocking`}
              />
              <Metric
                label="Issues resolved"
                value={String(report.quality.issues_resolved)}
              />
              <Metric label="Test files" value={String(report.quality.test_files)} />
            </div>
            {report.quality.assessment ? (
              <blockquote className="border-l-2 border-brand-500 pl-3 text-xs leading-relaxed text-content-muted">
                {report.quality.assessment}
              </blockquote>
            ) : null}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Token usage" description="Model consumption for this run" />
        <CardBody>
          <div className="grid gap-4 sm:grid-cols-4">
            <Metric label="Input" value={formatNumber(report.usage.input_tokens)} />
            <Metric label="Output" value={formatNumber(report.usage.output_tokens)} />
            <Metric label="Cache reads" value={formatNumber(report.usage.cache_read_tokens)} />
            <Metric label="Total" value={formatNumber(report.usage.total_tokens)} />
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string | undefined;
}) {
  return (
    <div className="rounded-lg bg-surface-sunken px-3 py-2.5">
      <p className="text-xs text-content-muted">{label}</p>
      <p className="mt-0.5 text-lg font-semibold tabular-nums text-content">{value}</p>
      {hint ? <p className="text-xs text-content-subtle">{hint}</p> : null}
    </div>
  );
}
