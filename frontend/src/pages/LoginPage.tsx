import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';

import { ApiError } from '@/api/client';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useAuth } from '@/hooks/useAuth';

export function LoginPage() {
  const { login, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? '/';

  if (!isLoading && isAuthenticated) {
    return <Navigate to={from} replace />;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Sign in failed. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Sign in to Aegis AI"
      subtitle="Your autonomous AI engineering team is standing by."
      footer={
        <>
          Don&apos;t have an account?{' '}
          <Link to="/register" className="rounded font-medium text-brand-400 hover:text-brand-300">
            Create one
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {error ? (
          <div
            className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger"
            role="alert"
          >
            {error}
          </div>
        ) : null}

        <Input
          label="Email address"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@company.com"
        />

        <Input
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="••••••••••"
        />

        <Button type="submit" fullWidth isLoading={isSubmitting} size="lg">
          Sign in
        </Button>
      </form>
    </AuthLayout>
  );
}

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen">
      {/* Brand panel, hidden below lg where the space is better spent on the form. */}
      <div className="relative hidden w-1/2 flex-col justify-between bg-gradient-to-br from-brand-800 via-brand-700 to-brand-900 p-12 lg:flex">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/15">
            <svg className="h-5 w-5 text-white" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 2l8 4v6c0 5.25-3.4 9.4-8 10.5C7.4 21.4 4 17.25 4 12V6l8-4z" />
            </svg>
          </div>
          <span className="text-lg font-semibold text-white">Aegis AI</span>
        </div>

        <div className="max-w-md">
          <h2 className="text-3xl font-semibold leading-tight text-white">
            From idea to production-ready starter project.
          </h2>
          <p className="mt-4 text-brand-100">
            Eleven specialised AI engineers analyse your requirements, design the
            architecture, write the code, review their own work and hand you a
            complete project.
          </p>
          <ul className="mt-8 space-y-3 text-sm text-brand-100">
            {[
              'Requirements, architecture and schema design',
              'Frontend, backend and database code',
              'Automated review and improvement pass',
              'Documentation, tests and a downloadable package',
            ].map((item) => (
              <li key={item} className="flex items-start gap-2.5">
                <svg className="mt-0.5 h-4 w-4 shrink-0 text-brand-300" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clipRule="evenodd" />
                </svg>
                {item}
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-brand-200">
          Aegis AI v1.0 — Multi-Agent AI Software Engineering Platform
        </p>
      </div>

      <div className="flex w-full items-center justify-center bg-surface px-4 py-12 lg:w-1/2">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600">
              <svg className="h-5 w-5 text-white" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M12 2l8 4v6c0 5.25-3.4 9.4-8 10.5C7.4 21.4 4 17.25 4 12V6l8-4z" />
              </svg>
            </div>
            <span className="font-semibold text-content">Aegis AI</span>
          </div>

          <h1 className="text-2xl font-semibold tracking-tight text-content">{title}</h1>
          <p className="mb-8 mt-1.5 text-sm text-content-muted">{subtitle}</p>

          {children}

          <p className="mt-6 text-center text-sm text-content-muted">{footer}</p>
        </div>
      </div>
    </div>
  );
}
