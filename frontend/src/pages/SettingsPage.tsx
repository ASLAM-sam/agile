import { useState, type FormEvent } from 'react';

import { ApiError } from '@/api/client';
import { authApi, systemApi } from '@/api/resources';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useAsync } from '@/hooks/useAsync';
import { useAuth } from '@/hooks/useAuth';
import { useTheme } from '@/hooks/useTheme';
import { formatDate } from '@/lib/utils';
import type { HealthStatus } from '@/types';

export function SettingsPage() {
  const { user, updateUser } = useAuth();
  const { theme, setTheme } = useTheme();
  const health = useAsync<HealthStatus>((signal) => systemApi.health(signal), []);

  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [error, setError] = useState<string | null>(null);

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    setStatus('saving');
    setError(null);
    try {
      const updated = await authApi.updateProfile({
        full_name: fullName.trim(),
        theme_preference: theme,
      });
      updateUser(updated);
      setStatus('saved');
      window.setTimeout(() => setStatus('idle'), 2500);
    } catch (caught) {
      setStatus('idle');
      setError(caught instanceof ApiError ? caught.message : 'The profile could not be saved.');
    }
  }

  return (
    <div className="mx-auto max-w-3xl animate-fade-in">
      <PageHeader title="Settings" description="Your profile and platform status" />

      <div className="space-y-6">
        <Card>
          <CardHeader title="Profile" />
          <CardBody>
            <form onSubmit={handleSave} className="space-y-4">
              {error ? (
                <div
                  className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger"
                  role="alert"
                >
                  {error}
                </div>
              ) : null}

              <Input
                label="Full name"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                minLength={2}
                required
              />

              <Input
                label="Email address"
                value={user?.email ?? ''}
                disabled
                readOnly
                hint="Your email address cannot be changed."
              />

              <fieldset>
                <legend className="mb-2 block text-sm font-medium text-content">Theme</legend>
                <div className="flex gap-2">
                  {(['dark', 'light'] as const).map((option) => (
                    <label
                      key={option}
                      className={
                        theme === option
                          ? 'flex cursor-pointer items-center gap-2 rounded-lg border border-brand-500 bg-brand-500/5 px-4 py-2 text-sm text-content'
                          : 'flex cursor-pointer items-center gap-2 rounded-lg border border-edge px-4 py-2 text-sm text-content-muted hover:border-content-subtle'
                      }
                    >
                      <input
                        type="radio"
                        name="theme"
                        value={option}
                        checked={theme === option}
                        onChange={() => setTheme(option)}
                        className="h-4 w-4 accent-brand-500"
                      />
                      {option === 'dark' ? 'Dark' : 'Light'}
                    </label>
                  ))}
                </div>
              </fieldset>

              <div className="flex items-center gap-3 border-t border-edge pt-4">
                <Button type="submit" isLoading={status === 'saving'}>
                  Save changes
                </Button>
                {status === 'saved' ? (
                  <span className="text-sm text-success" role="status">
                    Saved
                  </span>
                ) : null}
              </div>
            </form>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Platform status" />
          {health.isLoading ? (
            <LoadingState rows={2} />
          ) : health.error ? (
            <ErrorState error={health.error} onRetry={health.reload} />
          ) : health.data ? (
            <CardBody>
              <dl className="grid gap-4 sm:grid-cols-2">
                <Row label="Service">
                  <Badge tone={health.data.status === 'ok' ? 'success' : 'warning'}>
                    {health.data.status}
                  </Badge>
                </Row>
                <Row label="Version">
                  <span className="font-mono text-xs text-content-muted">
                    {health.data.version}
                  </span>
                </Row>
                <Row label="Environment">
                  <span className="text-xs text-content-muted">{health.data.environment}</span>
                </Row>
                <Row label="Database">
                  <Badge tone={health.data.database === 'connected' ? 'success' : 'danger'}>
                    {health.data.database}
                  </Badge>
                </Row>
                <Row label="Model provider">
                  <Badge tone={health.data.llm_configured ? 'success' : 'warning'}>
                    {health.data.llm_configured ? 'configured' : 'not configured'}
                  </Badge>
                </Row>
                <Row label="Active runs">
                  <span className="font-mono text-xs tabular-nums text-content-muted">
                    {health.data.active_runs}
                  </span>
                </Row>
              </dl>

              {!health.data.llm_configured ? (
                <p className="mt-4 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
                  Generation is disabled until <code>ANTHROPIC_API_KEY</code> is set in the
                  backend environment.
                </p>
              ) : null}
            </CardBody>
          ) : null}
        </Card>

        {user ? (
          <Card>
            <CardHeader title="Account" />
            <CardBody>
              <dl className="grid gap-4 sm:grid-cols-2">
                <Row label="Account ID">
                  <span className="font-mono text-xs text-content-muted">{user.id}</span>
                </Row>
                <Row label="Member since">
                  <span className="text-xs text-content-muted">
                    {formatDate(user.created_at)}
                  </span>
                </Row>
              </dl>
            </CardBody>
          </Card>
        ) : null}
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-content-subtle">{label}</dt>
      <dd className="mt-1">{children}</dd>
    </div>
  );
}
