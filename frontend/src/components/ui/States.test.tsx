import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/api/client';
import { EmptyState, ErrorState, LoadingState } from './States';

describe('LoadingState', () => {
  it('announces itself to assistive technology', () => {
    render(<LoadingState label="Loading projects…" />);

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText('Loading projects…')).toBeInTheDocument();
  });
});

describe('ErrorState', () => {
  it('renders the message in an alert region', () => {
    render(<ErrorState error={new ApiError(500, 'api_error', 'Something broke.')} />);

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Something broke.');
  });

  it('lists field-level validation problems', () => {
    const error = new ApiError(422, 'validation_error', 'Invalid input.', {
      errors: [{ loc: ['body', 'idea'], msg: 'too short' }],
    });
    render(<ErrorState error={error} />);

    expect(screen.getByText(/idea: too short/)).toBeInTheDocument();
  });

  it('offers a retry affordance when recovery is possible', async () => {
    const onRetry = vi.fn();
    render(<ErrorState error={new Error('Network down')} onRetry={onRetry} />);

    const button = screen.getByRole('button', { name: /try again/i });
    button.click();

    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('omits the retry button when no handler is given', () => {
    render(<ErrorState error={new Error('Fatal')} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('EmptyState', () => {
  it('explains the empty result and offers a next step', () => {
    render(
      <EmptyState
        title="No projects yet"
        description="Describe an idea to get started."
        action={<button type="button">Create project</button>}
      />,
    );

    expect(screen.getByText('No projects yet')).toBeInTheDocument();
    expect(screen.getByText('Describe an idea to get started.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create project' })).toBeInTheDocument();
  });
});
