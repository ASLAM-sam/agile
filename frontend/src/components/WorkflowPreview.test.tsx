import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { WorkflowPreview } from './WorkflowPreview';
import type { WorkflowStep } from '@/types';

function step(overrides: Partial<WorkflowStep> & Pick<WorkflowStep, 'role' | 'display_name' | 'sequence'>): WorkflowStep {
  return {
    status: 'waiting',
    skip_reason: '',
    depends_on: [],
    ...overrides,
  };
}

describe('WorkflowPreview', () => {
  const steps: WorkflowStep[] = [
    step({ role: 'manager', display_name: 'Manager', sequence: 0 }),
    step({ role: 'business_analyst', display_name: 'Business Analyst', sequence: 1 }),
    step({
      role: 'database_engineer',
      display_name: 'Database Engineer',
      sequence: 2,
      status: 'skipped',
      skip_reason: 'This project holds no persistent state.',
    }),
  ];

  it('shows how many agents will actually be engaged', () => {
    render(<WorkflowPreview steps={steps} />);
    expect(screen.getByText('2 of 3 agents will be engaged')).toBeInTheDocument();
  });

  it('lists every agent, including the skipped ones', () => {
    render(<WorkflowPreview steps={steps} />);

    expect(screen.getByText('Manager')).toBeInTheDocument();
    expect(screen.getByText('Business Analyst')).toBeInTheDocument();
    expect(screen.getByText('Database Engineer')).toBeInTheDocument();
  });

  it('explains why an agent was skipped rather than just hiding it', () => {
    render(<WorkflowPreview steps={steps} />);

    expect(
      screen.getByText('This project holds no persistent state.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/1 agent will be skipped because this project does not need/i),
    ).toBeInTheDocument();
  });

  it('says nothing about skips when every agent runs', () => {
    render(<WorkflowPreview steps={steps.slice(0, 2)} />);
    expect(screen.queryByText(/will be skipped/i)).not.toBeInTheDocument();
  });
});
