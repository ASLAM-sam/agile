/**
 * The four states every data-loading view must render.
 *
 * Centralised so a screen cannot accidentally ship with only the success path:
 * loading, error, empty and content each have a component here.
 */

import type { ReactNode } from 'react';

import { ApiError } from '@/api/client';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn('h-5 w-5 animate-spin text-brand-500', className)}
      viewBox="0 0 24 24"
      fill="none"
      role="status"
      aria-label="Loading"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}

export function LoadingState({
  label = 'Loading…',
  rows = 3,
}: {
  label?: string;
  rows?: number;
}) {
  return (
    <div className="space-y-3 p-6" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          className="skeleton h-12"
          style={{ opacity: 1 - index * 0.15 }}
          aria-hidden="true"
        />
      ))}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: ApiError | Error;
  onRetry?: () => void;
  className?: string;
}) {
  const problems = error instanceof ApiError ? error.validationProblems : [];

  return (
    <div
      className={cn('flex flex-col items-center gap-4 px-6 py-12 text-center', className)}
      role="alert"
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-danger/10">
        <svg
          className="h-6 w-6 text-danger"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
          />
        </svg>
      </div>
      <div className="max-w-md">
        <p className="text-sm font-medium text-content">{error.message}</p>
        {problems.length > 0 ? (
          <ul className="mt-2 space-y-1 text-xs text-content-muted">
            {problems.map((problem) => (
              <li key={problem}>• {problem}</li>
            ))}
          </ul>
        ) : null}
      </div>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-4 px-6 py-16 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-surface-sunken text-content-subtle">
        {icon ?? (
          <svg
            className="h-7 w-7"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z"
            />
          </svg>
        )}
      </div>
      <div className="max-w-sm">
        <p className="text-sm font-semibold text-content">{title}</p>
        {description ? (
          <p className="mt-1 text-sm text-content-muted">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  );
}
