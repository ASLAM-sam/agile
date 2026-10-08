/**
 * LLM Usage & Quota Observability Dashboard.
 *
 * Real-time monitoring for:
 * 1. Global LLM Usage (Requests, Tokens, Latency, Fallbacks)
 * 2. Usage by Agent
 * 3. Usage by Provider
 * 4. Usage by Model
 * 5. Credential Health & Cooldowns
 * 6. Live Quota (RPM, RPD, TPM) distinguishing Provider-reported vs Unknown
 * 7. Live Recent Requests Log
 */

import { useCallback, useEffect, useState } from 'react';

import { usageApi } from '@/api/resources';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useAsync } from '@/hooks/useAsync';

const REFRESH_MS = 6000;

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-lg border border-edge bg-surface-raised p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-content-muted">{label}</p>
      <p className="mt-1 truncate text-2xl font-semibold text-content">{value}</p>
      {hint ? <p className="mt-1 text-xs text-content-subtle">{hint}</p> : null}
    </div>
  );
}

export function UsageDashboardPage() {
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchTelemetry = useCallback(async (signal?: AbortSignal) => {
    const [summary, credentials, quota, recentLogs] = await Promise.all([
      usageApi.summary({}, signal),
      usageApi.credentials(signal),
      usageApi.quota(signal),
      usageApi.logs({ limit: 10 }, signal),
    ]);
    return { summary, credentials, quota, recentLogs };
  }, []);

  const { data, isLoading, error, reload } = useAsync(fetchTelemetry, []);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      reload();
    }, REFRESH_MS);
    return () => clearInterval(interval);
  }, [autoRefresh, reload]);

  if (isLoading && !data) {
    return <LoadingState label="Loading LLM usage telemetry..." />;
  }

  if (error && !data) {
    return <ErrorState error={error} onRetry={reload} />;
  }

  const summary = data?.summary || {};
  const credentials = data?.credentials || [];
  const quota = data?.quota || {};
  const recentLogs = data?.recentLogs?.items || [];

  return (
    <div className="space-y-8">
      <PageHeader
        title="LLM Usage & Quota Observability"
        description="Comprehensive accounting for every AI provider request, credential health status, and live quota limits."
        actions={
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setAutoRefresh((v) => !v)}
            >
              {autoRefresh ? 'Pause Auto-Refresh' : 'Enable Auto-Refresh'}
            </Button>
            <Button variant="secondary" size="sm" onClick={() => reload()}>
              Refresh Now
            </Button>
          </div>
        }
      />

      {/* 1. Global LLM Usage */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-content-muted">
          LLM Usage Overview
        </h2>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
          <Stat label="Total Requests" value={summary.total_requests ?? 0} />
          <Stat label="Successful" value={summary.successful_requests ?? 0} hint="Target: 10/task" />
          <Stat label="Failed" value={summary.failed_requests ?? 0} />
          <Stat label="Fallbacks" value={summary.fallback_requests ?? 0} hint="Failover activations" />
          <Stat label="Total Tokens" value={(summary.total_tokens ?? 0).toLocaleString()} />
          <Stat label="Avg Latency" value={`${Math.round(summary.average_latency_ms ?? 0)} ms`} />
        </div>
      </section>

      {/* 2. By Agent & 3. By Provider */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <h3 className="mb-4 text-base font-semibold text-content">Usage By Agent</h3>
          <div className="divide-y divide-edge">
            {Object.keys(summary.requests_by_agent || {}).length === 0 ? (
              <p className="py-4 text-sm text-content-muted">No agent requests recorded yet.</p>
            ) : (
              Object.entries(summary.requests_by_agent as Record<string, number>).map(([agent, count]) => (
                <div key={agent} className="flex items-center justify-between py-2 text-sm">
                  <span className="font-mono text-xs text-content">{agent}</span>
                  <span className="font-semibold text-content">{count} reqs</span>
                </div>
              ))
            )}
          </div>
        </Card>

        <Card className="p-5">
          <h3 className="mb-4 text-base font-semibold text-content">Usage By Provider</h3>
          <div className="divide-y divide-edge">
            {Object.keys(summary.requests_by_provider || {}).length === 0 ? (
              <p className="py-4 text-sm text-content-muted">No provider requests recorded yet.</p>
            ) : (
              Object.entries(summary.requests_by_provider as Record<string, number>).map(([provider, count]) => (
                <div key={provider} className="flex items-center justify-between py-2 text-sm">
                  <span className="font-medium capitalize text-content">{provider}</span>
                  <span className="font-semibold text-content">{count} reqs</span>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      {/* 4. By Model & By Credential */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <h3 className="mb-4 text-base font-semibold text-content">Usage By Model</h3>
          <div className="divide-y divide-edge">
            {Object.keys(summary.requests_by_model || {}).length === 0 ? (
              <p className="py-4 text-sm text-content-muted">No model requests recorded yet.</p>
            ) : (
              Object.entries(summary.requests_by_model as Record<string, number>).map(([model, count]) => (
                <div key={model} className="flex items-center justify-between py-2 text-sm">
                  <span className="font-mono text-xs text-content">{model}</span>
                  <span className="font-semibold text-content">{count} reqs</span>
                </div>
              ))
            )}
          </div>
        </Card>

        <Card className="p-5">
          <h3 className="mb-4 text-base font-semibold text-content">Usage By Credential Slot</h3>
          <div className="divide-y divide-edge">
            {Object.keys(summary.requests_by_credential || {}).length === 0 ? (
              <p className="py-4 text-sm text-content-muted">No credential activity recorded yet.</p>
            ) : (
              Object.entries(summary.requests_by_credential as Record<string, number>).map(([slot, count]) => (
                <div key={slot} className="flex items-center justify-between py-2 text-sm">
                  <span className="font-mono text-xs text-content">{slot}</span>
                  <span className="font-semibold text-content">{count} reqs</span>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      {/* 5. Credential Health & Cooldowns */}
      <Card className="p-5">
        <h3 className="mb-4 text-base font-semibold text-content">Credential Slot Health & Cooldowns</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-edge text-xs uppercase text-content-muted">
                <th className="pb-3">Slot</th>
                <th className="pb-3">Masked Key</th>
                <th className="pb-3">Status</th>
                <th className="pb-3">Requests</th>
                <th className="pb-3">Success</th>
                <th className="pb-3">Failures</th>
                <th className="pb-3">Rate Limits</th>
                <th className="pb-3">Cooldown</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {credentials.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-4 text-center text-content-muted">
                    No credential slots registered.
                  </td>
                </tr>
              ) : (
                credentials.map((cred: any) => {
                  let tone: BadgeTone = 'success';
                  if (cred.status === 'cooling_down') tone = 'warning';
                  else if (cred.status === 'auth_failed') tone = 'danger';
                  else if (cred.status === 'exhausted') tone = 'danger';

                  return (
                    <tr key={cred.credential_slot}>
                      <td className="py-3 font-mono text-xs text-content">{cred.credential_slot}</td>
                      <td className="py-3 font-mono text-xs text-content-subtle">{cred.masked_credential}</td>
                      <td className="py-3">
                        <Badge tone={tone}>{cred.status}</Badge>
                      </td>
                      <td className="py-3 text-content">{cred.total_requests}</td>
                      <td className="py-3 text-emerald-600">{cred.successful_requests}</td>
                      <td className="py-3 text-rose-500">{cred.failed_requests}</td>
                      <td className="py-3 text-content">{cred.rate_limit_count}</td>
                      <td className="py-3 text-xs text-content-subtle">
                        {cred.is_cooling_down ? cred.cooldown_reason || 'Active' : '—'}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* 6. Live Quota Overview */}
      <Card className="p-5">
        <h3 className="mb-4 text-base font-semibold text-content">Quota Telemetry</h3>
        <p className="mb-4 text-xs text-content-subtle">
          Values are confirmed via vendor response headers where exposed; unexposed values remain strictly Unknown.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-edge text-xs uppercase text-content-muted">
                <th className="pb-3">Entity</th>
                <th className="pb-3">Type</th>
                <th className="pb-3">RPM (Used / Limit)</th>
                <th className="pb-3">RPD (Used / Limit)</th>
                <th className="pb-3">TPM (Used / Limit)</th>
                <th className="pb-3">Remaining RPM</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {((quota.providers || []) as any[]).concat(quota.models || []).length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-4 text-center text-content-muted">
                    No quota dimensions tracked yet.
                  </td>
                </tr>
              ) : (
                ((quota.providers || []) as any[]).concat(quota.models || []).map((item: any, idx: number) => (
                  <tr key={`${item.dimension}-${item.name}-${idx}`}>
                    <td className="py-3 font-medium text-content">{item.name}</td>
                    <td className="py-3 text-xs capitalize text-content-subtle">{item.dimension}</td>
                    <td className="py-3 text-xs text-content">
                      {item.rpm?.used ?? 0} / {item.rpm?.limit ?? 'Unknown'}
                    </td>
                    <td className="py-3 text-xs text-content">
                      {item.rpd?.used ?? 0} / {item.rpd?.limit ?? 'Unknown'}
                    </td>
                    <td className="py-3 text-xs text-content">
                      {item.tpm?.used ?? 0} / {item.tpm?.limit ?? 'Unknown'}
                    </td>
                    <td className="py-3 text-xs">
                      {item.rpm?.remaining !== null ? (
                        <span className="font-semibold text-emerald-600">{item.rpm.remaining}</span>
                      ) : (
                        <span className="text-content-muted">Unknown</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* 7. Recent Requests Log */}
      <Card className="p-5">
        <h3 className="mb-4 text-base font-semibold text-content">Recent Provider Requests</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-edge text-xs uppercase text-content-muted">
                <th className="pb-3">#</th>
                <th className="pb-3">Agent</th>
                <th className="pb-3">Provider / Model</th>
                <th className="pb-3">Slot</th>
                <th className="pb-3">Status</th>
                <th className="pb-3">Tokens</th>
                <th className="pb-3">Latency</th>
                <th className="pb-3">Fallback</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {recentLogs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-4 text-center text-content-muted">
                    No requests logged yet.
                  </td>
                </tr>
              ) : (
                recentLogs.map((log: any) => (
                  <tr key={log.id}>
                    <td className="py-3 font-mono text-xs text-content-subtle">#{log.request_number}</td>
                    <td className="py-3 font-mono text-xs text-content">{log.agent_role}</td>
                    <td className="py-3 text-xs text-content">
                      <span className="font-semibold capitalize">{log.provider}</span> / {log.model}
                    </td>
                    <td className="py-3 font-mono text-xs text-content-subtle">{log.credential_slot}</td>
                    <td className="py-3">
                      <Badge tone={log.status === 'success' ? 'success' : 'danger'}>{log.status}</Badge>
                    </td>
                    <td className="py-3 text-xs text-content">
                      {log.total_tokens !== null ? log.total_tokens.toLocaleString() : '—'}
                    </td>
                    <td className="py-3 text-xs text-content">{Math.round(log.latency_ms)} ms</td>
                    <td className="py-3 text-xs">
                      {log.fallback_used ? (
                        <span className="text-warning">Yes ({log.fallback_from} &rarr; {log.fallback_to})</span>
                      ) : (
                        <span className="text-content-muted">No</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
