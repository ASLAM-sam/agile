import type { Run } from '@/types';
import { Button } from './ui/Button';

export interface GenerationResultProps {
  run: Run;
  onDownload: () => void;
  isDownloading?: boolean;
}

export function GenerationResult({
  run,
  onDownload,
  isDownloading = false,
}: GenerationResultProps) {
  const isFailed = run.status === 'failed';
  const hasPartialArtifact =
    isFailed && Boolean(
      run.artifact?.available ??
      run.artifact_available ??
      (run.file_count && run.file_count > 0) ??
      ((run.artifact_count ?? 0) > 0)
    );

  if (isFailed && hasPartialArtifact) {
    return (
      <div
        className="mb-6 overflow-hidden rounded-xl border border-amber-500/30 bg-amber-950/20 p-5 backdrop-blur-sm"
        role="region"
        aria-label="Generation Failure and Preserved Artifact"
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center rounded-md bg-amber-500/20 px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-amber-300 ring-1 ring-inset ring-amber-500/30">
                RELEASE BLOCKED
              </span>
              <span className="text-sm font-medium text-amber-200">
                Partial Artifact Preserved
              </span>
            </div>
            <p className="text-sm text-content-muted">
              {run.error_message ||
                'Validation or execution failed. The workspace at failure has been preserved.'}
            </p>
            <div className="flex items-center gap-2 pt-1 text-xs font-medium text-amber-400">
              <svg
                className="h-4 w-4 shrink-0 text-amber-400"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth="2"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
                />
              </svg>
              <span>This is NOT production-ready. Generated files are provided for inspection and debugging.</span>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-3">
            <Button
              variant="secondary"
              onClick={onDownload}
              isLoading={isDownloading}
              className="border-amber-500/40 bg-amber-900/30 text-amber-100 hover:bg-amber-800/40"
              id="download-partial-artifact-btn"
            >
              Download Partial ZIP
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (run.status === 'completed') {
    return (
      <div
        className="mb-6 flex flex-col gap-4 rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-5 backdrop-blur-sm sm:flex-row sm:items-center sm:justify-between"
        role="region"
        aria-label="Generation Complete and Release Ready"
      >
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center rounded-md bg-emerald-500/20 px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-emerald-300 ring-1 ring-inset ring-emerald-500/30">
            RELEASE OK
          </span>
          <span className="text-sm font-medium text-emerald-200">
            Generation Complete
          </span>
        </div>
        <Button
          onClick={onDownload}
          isLoading={isDownloading}
          id="download-full-artifact-btn"
        >
          Download ZIP
        </Button>
      </div>
    );
  }

  return null;
}
