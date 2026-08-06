import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';

import { ApiError } from '@/api/client';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useAuth } from '@/hooks/useAuth';
import { AuthLayout } from '@/pages/LoginPage';

const MIN_PASSWORD_LENGTH = 10;

export function RegisterPage() {
  const { register, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [isSubmitting, setSubmitting] = useState(false);

  if (!isLoading && isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  // Mirrors the server rule so the user is told before a round trip, not after.
  const passwordProblem =
    password.length > 0 && password.length < MIN_PASSWORD_LENGTH
      ? `Use at least ${MIN_PASSWORD_LENGTH} characters.`
      : password.length > 0 && (/^[a-zA-Z]+$/.test(password) || /^\d+$/.test(password))
        ? 'Combine letters with numbers or symbols.'
        : undefined;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setProblems([]);
    setSubmitting(true);
    try {
      await register(email, fullName, password);
      navigate('/', { replace: true });
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setProblems(caught.validationProblems);
      } else {
        setError('Registration failed. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Start turning ideas into engineered projects."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="rounded font-medium text-brand-400 hover:text-brand-300">
            Sign in
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
            <p>{error}</p>
            {problems.length > 0 ? (
              <ul className="mt-1.5 space-y-0.5 text-xs">
                {problems.map((problem) => (
                  <li key={problem}>• {problem}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        <Input
          label="Full name"
          autoComplete="name"
          required
          minLength={2}
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
          placeholder="Ada Lovelace"
        />

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
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="••••••••••"
          hint={`At least ${MIN_PASSWORD_LENGTH} characters, mixing letters with numbers or symbols.`}
          {...(passwordProblem ? { error: passwordProblem } : {})}
        />

        <Button
          type="submit"
          fullWidth
          size="lg"
          isLoading={isSubmitting}
          disabled={passwordProblem !== undefined}
        >
          Create account
        </Button>
      </form>
    </AuthLayout>
  );
}
