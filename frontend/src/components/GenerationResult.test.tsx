import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { GenerationResult } from './GenerationResult';
import type { Run } from '@/types';

describe('GenerationResult', () => {
  it('displays RELEASE BLOCKED, non-production warning, and partial download action when run fails with preserved files', () => {
    const onDownload = vi.fn();
    const run: Run = {
      id: 'run-fail-1',
      project_id: 'proj-1',
      status: 'failed',
      phase: 'failed',
      progress: 50,
      file_count: 5,
      duration_seconds: 12,
      created_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
      error_message: 'TypeScript build failed: Property title does not exist',
      release_eligible: false,
      artifact: {
        available: true,
        type: 'partial',
        name: 'project-partial.zip',
      },
    };

    render(
      <GenerationResult
        run={run}
        onDownload={onDownload}
      />,
    );

    expect(screen.getByText('RELEASE BLOCKED')).toBeInTheDocument();
    expect(screen.getByText('Partial Artifact Preserved')).toBeInTheDocument();
    expect(screen.getByText(/This is NOT production-ready/i)).toBeInTheDocument();

    const downloadBtn = screen.getByRole('button', { name: /Download Partial ZIP/i });
    expect(downloadBtn).toBeInTheDocument();

    fireEvent.click(downloadBtn);
    expect(onDownload).toHaveBeenCalledTimes(1);
  });

  it('displays RELEASE OK and full download button when run completes successfully', () => {
    const onDownload = vi.fn();
    const run: Run = {
      id: 'run-success-1',
      project_id: 'proj-1',
      status: 'completed',
      phase: 'complete',
      progress: 100,
      file_count: 12,
      duration_seconds: 45,
      created_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
      release_eligible: true,
      artifact: {
        available: true,
        type: 'full',
        name: 'project.zip',
      },
    };

    render(
      <GenerationResult
        run={run}
        onDownload={onDownload}
      />,
    );

    expect(screen.getByText('RELEASE OK')).toBeInTheDocument();
    expect(screen.getByText('Generation Complete')).toBeInTheDocument();
    const downloadBtn = screen.getByRole('button', { name: /Download ZIP/i });
    expect(downloadBtn).toBeInTheDocument();

    fireEvent.click(downloadBtn);
    expect(onDownload).toHaveBeenCalledTimes(1);
  });

  it('displays Download Partial ZIP when artifact_available root property is true', () => {
    const onDownload = vi.fn();
    const run: Run = {
      id: 'run-fail-root-props',
      project_id: 'proj-1',
      status: 'failed',
      phase: 'failed',
      progress: 60,
      file_count: 8,
      duration_seconds: 15,
      created_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
      release_eligible: false,
      artifact_available: true,
      artifact_type: 'partial',
      artifact_name: 'project-partial.zip',
    };

    render(
      <GenerationResult
        run={run}
        onDownload={onDownload}
      />,
    );

    expect(screen.getByText('RELEASE BLOCKED')).toBeInTheDocument();
    expect(screen.getByText('Partial Artifact Preserved')).toBeInTheDocument();
    const downloadBtn = screen.getByRole('button', { name: /Download Partial ZIP/i });
    expect(downloadBtn).toBeInTheDocument();
    fireEvent.click(downloadBtn);
    expect(onDownload).toHaveBeenCalledTimes(1);
  });

  it('renders nothing when run is pending without failure', () => {
    const onDownload = vi.fn();
    const run: Run = {
      id: 'run-running-1',
      project_id: 'proj-1',
      status: 'running',
      phase: 'frontend',
      progress: 30,
      file_count: 0,
      duration_seconds: 5,
      created_at: new Date().toISOString(),
      finished_at: null,
      release_eligible: false,
    };

    const { container } = render(
      <GenerationResult
        run={run}
        onDownload={onDownload}
      />,
    );

    expect(container.firstChild).toBeNull();
  });
});
