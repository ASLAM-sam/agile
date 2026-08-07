/**
 * Provider monitor.
 *
 * Shows which model provider is serving requests, which ones are standing by,
 * and which have been withdrawn after a quota or a run of failures. The whole
 * point of failover is that it happens without the user doing anything, so the
 * value of this screen is answering "what did it do, and why" after the fact.
 *
 * Polls rather than streams: provider health changes on the timescale of a
 * request, and an SSE topic for a handful of counters would cost more than it
 * saves.
 */

import { useCallback, useEffect, useState } from 'react';

import { providerApi } from '@/api/resources';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useAsync } from '@/hooks/useAsync';
import { cn } from '@/lib/utils';
import type { ProviderHealth } from '@/types';

const REFRESH_MS = 5000;

const STATUS_TONE: Record<ProviderHealth['status'], BadgeTone> = {
  healthy: 'success',
  degraded: 'warning',
  cooling_down: 'danger',
  unconfigured: 'muted',
  disabled: 'neutral',
};

const STATUS_LABEL: Record<ProviderHealth['status'], string> = {
  healthy: 'Healthy',
  degraded: 'Degraded',
  cooling_down: 'Cooling down',
  unconfigured: 'No credentials',
  disabled: 'Disabled',
};

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function latency(ms: number): string {
  if (!ms) return '—';
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-edge bg-surface-raised p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-content-muted">{label}</p>
      <p className="mt-1 truncate text-2xl font-semibold text-content">{value}</p>
      {hint ? <p className="mt-1 text-xs text-content-subtle">{hint}</p> : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-content-subtle">{label}</dt>
      <dd className="font-medium text-content">{value}</dd>
    </div>
  );
}

function ProviderRow({
  provider,
  isActive,
  onReset,
  resetting,
}: {
  provider: ProviderHealth;
  isActive: boolean;
  onReset: (key: string) => void;
  resetting: boolean;
}) {
  const cooling = provider.status === 'cooling_down';

  return (
    <div
      className={cn(
        'rounded-lg border p-4 transition-colors',
        isActive ? 'border-brand-500 bg-brand-500/5' : 'border-edge bg-surface',
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-content">{provider.display_name}</span>
            <Badge tone={STATUS_TONE[provider.status]}>{STATUS_LABEL[provider.status]}</Badge>
            {isActive ? <Badge tone="brand">Active</Badge> : null}
            <span className="text-xs text-content-subtle">priority {provider.priority + 1}</span>
          </div>
          <p className="mt-1 truncate font-mono text-xs text-content-muted">
            {provider.model || '—'}
          </p>
        </div>

        {cooling ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => onReset(provider.key)}
            disabled={resetting}
          >
            {resetting ? 'Restoring…' : 'Restore now'}
          </Button>
        ) : null}
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <Metric label="Requests" value={String(provider.requests)} />
        <Metric
          label="Success rate"
          value={provider.requests ? percent(provider.success_rate) : '—'}
        />
        <Metric label="Latency" value={latency(provider.latency_ms)} />
        <Metric label="Retries" value={String(provider.retries)} />
        <Metric label="Handed away" value={String(provider.failovers_from)} />
        <Metric label="Picked up" value={String(provider.failovers_to)} />
        <Metric label="Tokens in" value={provider.input_tokens.toLocaleString()} />
        <Metric label="Tokens out" value={provider.output_tokens.toLocaleString()} />
      </dl>

      {cooling && provider.cooldown_reason ? (
        <p className="mt-3 rounded-md bg-danger/10 px-3 py-2 text-xs text-danger">
          {provider.cooldown_reason} Back in {Math.ceil(provider.cooldown_remaining_seconds)}s.
        </p>
      ) : null}

      {!cooling && provider.last_error ? (
        <p className="mt-3 truncate text-xs text-content-subtle" title={provider.last_error}>
          Last error ({provider.last_error_kind}): {provider.last_error}
        </p>
      ) : null}

      {provider.status === 'unconfigured' ? (
        <p className="mt-3 text-xs text-content-subtle">
          Add this provider&apos;s API key in <code>backend/.env</code> to bring it into the
          rotation.
        </p>
      ) : null}
    </div>
  );
}

export function ProvidersPage() {
  const [tick, setTick] = useState(0);
  const [resetting, setResetting] = useState<string | null>(null);

  const state = useAsync((signal) => providerApi.dashboard(signal), [tick]);

  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), REFRESH_MS);
    return () => window.clearInterval(id);
  }, []);

  const handleReset = useCallback(async (key: string) => {
    setResetting(key);
    try {
      await providerApi.reset(key);
      setTick((n) => n + 1);
    } finally {
      setResetting(null);
    }
  }, []);

  if (state.isLoading) return <LoadingState label="Reading provider health…" />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;
  if (!state.data) return null;

  const data = state.data;
  const activeProvider = data.providers.find((p) => p.key === data.active_provider);
  const firstAvailable = data.available_providers[0];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Providers"
        description="Which model provider is serving requests, and what happened when one could not."
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Active provider"
          value={activeProvider?.display_name ?? firstAvailable ?? 'None'}
          hint={`${data.available_providers.length} of ${data.providers.length} available`}
        />
        <Stat
          label="Requests"
          value={data.totals.requests.toLocaleString()}
          hint={
            data.totals.requests
              ? `${percent(data.totals.success_rate)} succeeded`
              : 'No traffic yet'
          }
        />
        <Stat
          label="Automatic failovers"
          value={data.totals.failovers.toLocaleString()}
          hint={`${data.totals.retries} retries`}
        />
        <Stat
          label="Cache hits"
          value={data.cache.hits.toLocaleString()}
          hint={
            data.cache.lookups ? `${percent(data.cache.hit_rate)} of lookups` : 'No lookups yet'
          }
        />
      </div>

      {data.available_providers.length === 0 ? (
        <Card className="border-danger/40 bg-danger/5 p-4">
          <p className="text-sm text-danger">
            No provider is currently available. Generation is disabled until at least one
            provider has credentials and is out of cooldown.
          </p>
        </Card>
      ) : null}

      <Card className="p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold text-content">Routing order</h2>
            <p className="text-sm text-content-muted">
              Tried top to bottom. A provider that cannot serve a request hands it to the next
              one automatically.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge tone={data.failover_enabled ? 'success' : 'neutral'}>
              Failover {data.failover_enabled ? 'on' : 'off'}
            </Badge>
            <Badge tone={data.task_routing_enabled ? 'success' : 'neutral'}>
              Task routing {data.task_routing_enabled ? 'on' : 'off'}
            </Badge>
            <Badge tone={data.cache_enabled ? 'success' : 'neutral'}>
              Cache {data.cache_enabled ? 'on' : 'off'}
            </Badge>
            <Badge tone="neutral">{data.retry_limit} retries each</Badge>
          </div>
        </div>

        <div className="space-y-3">
          {data.providers.map((provider) => (
            <ProviderRow
              key={provider.key}
              provider={provider}
              isActive={provider.key === data.active_provider}
              onReset={handleReset}
              resetting={resetting === provider.key}
            />
          ))}
        </div>
      </Card>
    </div>
  );
}
