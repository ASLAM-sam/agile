import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import type { AdapterKind, Capabilities, ScoredOption, TechStack } from '@/types';

interface Layer {
  kind: AdapterKind;
  label: string;
  capability: keyof Capabilities;
}

const LAYERS: Layer[] = [
  { kind: 'frontend', label: 'Frontend', capability: 'needs_frontend' },
  { kind: 'backend', label: 'Backend', capability: 'needs_backend' },
  { kind: 'database', label: 'Database', capability: 'needs_database' },
];

/**
 * Technology selection.
 *
 * Every option shows the reasoning that produced its ranking, so the user is
 * choosing between arguments rather than accepting an opaque recommendation.
 */
export function StackSelector({
  options,
  recommended,
  capabilities,
  value,
  onChange,
}: {
  options: Record<AdapterKind, ScoredOption[]>;
  recommended: TechStack;
  capabilities: Capabilities;
  value: Partial<TechStack>;
  onChange: (stack: Partial<TechStack>) => void;
}) {
  const activeLayers = LAYERS.filter((layer) => capabilities[layer.capability]);
  const isCustomised = activeLayers.some(
    (layer) => value[layer.kind] !== recommended[layer.kind],
  );

  return (
    <Card>
      <CardHeader
        title="Technology stack"
        description="Recommended for this project — change anything you like"
        action={isCustomised ? <Badge tone="warning">Customised</Badge> : null}
      />
      <CardBody className="space-y-5">
        {activeLayers.length === 0 ? (
          <p className="text-xs text-content-muted">
            This project needs no technology selection.
          </p>
        ) : null}

        {activeLayers.map((layer) => {
          const layerOptions = options[layer.kind] ?? [];
          const selected = value[layer.kind] ?? recommended[layer.kind];

          return (
            <fieldset key={layer.kind}>
              <legend className="mb-2 text-xs font-medium uppercase tracking-wide text-content-subtle">
                {layer.label}
              </legend>
              <div className="space-y-2">
                {layerOptions.map((option, index) => {
                  const isSelected = option.key === selected;
                  const isRecommended = option.key === recommended[layer.kind];

                  return (
                    <label
                      key={option.key}
                      className={cn(
                        'flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors',
                        isSelected
                          ? 'border-brand-500 bg-brand-500/5'
                          : 'border-edge hover:border-content-subtle',
                      )}
                    >
                      <input
                        type="radio"
                        name={`stack-${layer.kind}`}
                        value={option.key}
                        checked={isSelected}
                        onChange={() => onChange({ ...value, [layer.kind]: option.key })}
                        className="mt-0.5 h-4 w-4 shrink-0 accent-brand-500"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium text-content">
                            {option.display_name}
                          </span>
                          {isRecommended ? (
                            <Badge tone="brand">Recommended</Badge>
                          ) : index === 0 ? null : null}
                        </div>
                        {option.reasons.length > 0 ? (
                          <ul className="mt-1 space-y-0.5">
                            {option.reasons.slice(0, 2).map((reason) => (
                              <li key={reason} className="text-xs leading-relaxed text-content-muted">
                                {reason}
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          );
        })}

        {capabilities.needs_authentication ? (
          <div className="rounded-lg bg-surface-sunken px-3 py-2.5">
            <p className="text-xs font-medium text-content">
              Authentication: {recommended.authentication ?? 'JWT'}
            </p>
            {recommended.rationale['authentication'] ? (
              <p className="mt-0.5 text-xs text-content-muted">
                {recommended.rationale['authentication']}
              </p>
            ) : null}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}
