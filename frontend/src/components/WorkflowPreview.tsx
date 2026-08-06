import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { cn } from '@/lib/utils';
import type { WorkflowStep } from '@/types';

/**
 * The execution plan before a run starts.
 *
 * Shows which agents will be engaged and — just as usefully — which will be
 * skipped and why, so the dynamic workflow is legible rather than mysterious.
 */
export function WorkflowPreview({ steps }: { steps: WorkflowStep[] }) {
  const active = steps.filter((step) => step.status !== 'skipped');
  const skipped = steps.filter((step) => step.status === 'skipped');

  return (
    <Card>
      <CardHeader
        title="Execution plan"
        description={`${active.length} of ${steps.length} agents will be engaged`}
      />
      <CardBody>
        <ol className="space-y-0">
          {steps.map((step, index) => {
            const isSkipped = step.status === 'skipped';
            const isLast = index === steps.length - 1;

            return (
              <li key={step.role} className="relative flex gap-3 pb-3 last:pb-0">
                {!isLast ? (
                  <span
                    className="absolute left-[11px] top-6 h-full w-px bg-edge"
                    aria-hidden="true"
                  />
                ) : null}

                <span
                  className={cn(
                    'relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full',
                    'font-mono text-[10px] font-semibold',
                    isSkipped
                      ? 'bg-surface-sunken text-content-subtle'
                      : 'bg-brand-500/15 text-brand-400',
                  )}
                >
                  {index + 1}
                </span>

                <div className="min-w-0 flex-1 pt-0.5">
                  <p
                    className={cn(
                      'text-sm',
                      isSkipped
                        ? 'text-content-subtle line-through'
                        : 'font-medium text-content',
                    )}
                  >
                    {step.display_name}
                  </p>
                  {isSkipped && step.skip_reason ? (
                    <p className="mt-0.5 text-xs leading-relaxed text-content-muted">
                      {step.skip_reason}
                    </p>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>

        {skipped.length > 0 ? (
          <p className="mt-4 border-t border-edge pt-3 text-xs text-content-muted">
            {skipped.length} agent{skipped.length === 1 ? '' : 's'} will be skipped because
            this project does not need what they produce.
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}
