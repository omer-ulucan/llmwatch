/**
 * Component: ModelPicker
 * Purpose: The shared model selector for chat, agent and evals.
 * WHY: One searchable list, grouped by provider, showing price and capabilities, so
 * choosing a model is the same everywhere and costs are visible before running.
 */
import React, { useMemo, useState } from 'react';
import * as Popover from '@radix-ui/react-popover';
import { Link } from 'react-router';
import { Check, ChevronDown, Search, Star } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAvailableModels } from '@/hooks/useModels';
import type { ModelInfo } from '@/types';
import { priceLabel } from '@/lib/models';
import { CapabilityBadges } from './ModelBadges';

interface ModelPickerProps {
  /** Selected model id ("" for none). */
  value: string;
  onChange: (model: ModelInfo) => void;
  /** Only offer models with this capability (e.g. "tools" for the agent). */
  requireCapability?: keyof ModelInfo['capabilities'];
  id?: string;
  className?: string;
}

export const ModelPicker: React.FC<ModelPickerProps> = ({ value, onChange, requireCapability, id, className }) => {
  const { models, isLoading } = useAvailableModels();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [openWeightsOnly, setOpenWeightsOnly] = useState(false);
  const [localOnly, setLocalOnly] = useState(false);

  const selected = models.find((m) => m.id === value);

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = models.filter(
      (m) =>
        (!openWeightsOnly || m.open_weights) &&
        (!localOnly || m.local) &&
        (!needle || [m.display_name, m.model_id, m.provider_name].some((s) => s.toLowerCase().includes(needle))),
    );
    const byProvider = new Map<string, ModelInfo[]>();
    for (const m of filtered) byProvider.set(m.provider_name, [...(byProvider.get(m.provider_name) ?? []), m]);
    return [...byProvider.entries()];
  }, [models, query, openWeightsOnly, localOnly]);

  const lacks = (m: ModelInfo) => Boolean(requireCapability && !m.capabilities[requireCapability]);

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          id={id}
          type="button"
          className={cn(
            'flex w-full items-center justify-between gap-2 rounded-xl border border-card-border bg-black/30 px-3 py-2 text-left text-sm transition-colors hover:border-white/20 focus:outline-none focus:border-primary/60 cursor-pointer',
            className,
          )}
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          <span className="min-w-0">
            {selected ? (
              <>
                <span className="block truncate font-medium">{selected.display_name}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {selected.provider_name} · {priceLabel(selected)}
                </span>
              </>
            ) : (
              <span className="text-muted-foreground">{isLoading ? 'Loading models…' : 'Choose a model'}</span>
            )}
          </span>
          <ChevronDown size={16} className="shrink-0 text-muted-foreground" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          className="z-50 w-[min(26rem,calc(100vw-2rem))] rounded-2xl border border-card-border bg-card p-2 shadow-2xl"
        >
          <div className="flex items-center gap-2 rounded-xl bg-black/30 px-3">
            <Search size={14} className="text-muted-foreground" aria-hidden />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search models"
              aria-label="Search models"
              className="h-9 w-full bg-transparent text-sm focus:outline-none"
            />
          </div>
          <div className="mt-2 flex gap-2 px-1 text-xs">
            {[
              { label: 'Open weights', on: openWeightsOnly, set: setOpenWeightsOnly },
              { label: 'Local', on: localOnly, set: setLocalOnly },
            ].map((f) => (
              <button
                key={f.label}
                type="button"
                onClick={() => f.set(!f.on)}
                aria-pressed={f.on}
                className={cn(
                  'rounded-full border px-2.5 py-1 transition-colors cursor-pointer',
                  f.on ? 'border-primary/40 bg-primary/10 text-primary' : 'border-card-border text-muted-foreground hover:text-foreground',
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="mt-2 max-h-80 overflow-y-auto" role="listbox" aria-label="Models">
            {models.length === 0 && !isLoading && (
              <div className="px-3 py-6 text-center text-sm text-muted-foreground">
                No models configured yet.{' '}
                <Link to="/models" className="text-primary hover:underline" onClick={() => setOpen(false)}>
                  Add a provider
                </Link>
              </div>
            )}
            {models.length > 0 && groups.length === 0 && (
              <div className="px-3 py-6 text-center text-sm text-muted-foreground">No models match.</div>
            )}
            {groups.map(([provider, list]) => (
              <div key={provider} className="py-1">
                <div className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {provider}
                </div>
                {list.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    role="option"
                    aria-selected={m.id === value}
                    disabled={lacks(m)}
                    title={lacks(m) ? `This model isn't marked as supporting ${requireCapability}` : undefined}
                    onClick={() => {
                      onChange(m);
                      setOpen(false);
                    }}
                    className="flex w-full items-start gap-2 rounded-xl px-3 py-2 text-left hover:bg-white/[0.04] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                  >
                    <span className="mt-0.5 w-4 shrink-0 text-primary">{m.id === value && <Check size={14} />}</span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5">
                        <span className="truncate text-sm font-medium">{m.display_name}</span>
                        {m.is_default && <Star size={12} className="shrink-0 fill-warning text-warning" aria-label="default" />}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {m.model_id !== m.display_name ? `${m.model_id} · ` : ''}
                        {priceLabel(m)}
                      </span>
                      <span className="mt-1 block">
                        <CapabilityBadges model={m} />
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            ))}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
};
