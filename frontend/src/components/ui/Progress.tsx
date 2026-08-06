import { cn } from '@/lib/utils';

export type ProgressTone = 'brand' | 'success' | 'danger' | 'muted';

const TONES: Record<ProgressTone, string> = {
  brand: 'bg-brand-500',
  success: 'bg-success',
  danger: 'bg-danger',
  muted: 'bg-content-subtle',
};

export function ProgressBar({
  value,
  tone = 'brand',
  label,
  showValue = false,
  size = 'md',
  animated = false,
}: {
  value: number;
  tone?: ProgressTone;
  label?: string;
  showValue?: boolean;
  size?: 'sm' | 'md';
  animated?: boolean;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));

  return (
    <div className="w-full">
      {label || showValue ? (
        <div className="mb-1.5 flex items-baseline justify-between gap-2">
          {label ? <span className="text-xs text-content-muted">{label}</span> : null}
          {showValue ? (
            <span className="font-mono text-xs tabular-nums text-content-muted">
              {clamped}%
            </span>
          ) : null}
        </div>
      ) : null}
      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? 'Progress'}
        className={cn(
          'w-full overflow-hidden rounded-full bg-surface-sunken',
          size === 'sm' ? 'h-1' : 'h-1.5',
        )}
      >
        <div
          className={cn(
            'h-full rounded-full transition-[width] duration-500 ease-out',
            TONES[tone],
            animated && 'animate-pulse',
          )}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}

/** Blocky progress meter used in the agent monitor. */
export function BlockMeter({
  value,
  tone = 'brand',
  blocks = 10,
}: {
  value: number;
  tone?: ProgressTone;
  blocks?: number;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const filled = Math.round((clamped / 100) * blocks);

  return (
    <div
      className="flex gap-0.5"
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      {Array.from({ length: blocks }, (_, index) => (
        <span
          key={index}
          className={cn(
            'h-3 w-1.5 rounded-[2px] transition-colors duration-300',
            index < filled ? TONES[tone] : 'bg-surface-sunken',
          )}
          aria-hidden="true"
        />
      ))}
    </div>
  );
}
