/**
 * Start runs of a suite: one per model variant, compared later against each other
 * or against the suite's baseline.
 */
import React, { useCallback, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { Plus, X } from 'lucide-react';
import { evalsApi } from '@/api/evals';
import { getErrorMessage } from '@/api/errors';
import { ModelPicker } from '@/components/models/ModelPicker';
import { Button, Dialog, Field, Input, Switch, toast } from '@/components/ui';
import { useAvailableModels, useInitialModel } from '@/hooks/useModels';
import { variantLabels } from '@/lib/evals';
import type { VariantInput } from '@/types';

interface Variant {
  model: string;
  temperature: string;
}

interface NewRunDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  suiteId: string;
  /** Suite version to run (latest when omitted). */
  version?: number;
}

export const NewRunDialog: React.FC<NewRunDialogProps> = ({ open, onOpenChange, suiteId, version }) => {
  const [variants, setVariants] = useState<Variant[]>([{ model: '', temperature: '0' }]);
  const [repeats, setRepeats] = useState(1);
  const [concurrency, setConcurrency] = useState(4);
  const [judge, setJudge] = useState('');
  const [thinking, setThinking] = useState(false);
  const [useCache, setUseCache] = useState(true);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setFirstModel = useCallback(
    (model: string) => setVariants((all) => all.map((v, i) => (i === 0 ? { ...v, model } : v))),
    [],
  );
  useInitialModel(variants[0]?.model ?? '', setFirstModel);
  const { models } = useAvailableModels();

  const start = useMutation({
    mutationFn: () => {
      const labels = variantLabels(variants, (id) => models.find((m) => m.id === id)?.ref ?? id);
      return evalsApi.startRuns({
        suite_id: suiteId,
        version,
        variants: variants.map(
          (v, i): VariantInput => ({
            model: v.model,
            label: labels[i],
            temperature: v.temperature === '' ? undefined : Number(v.temperature),
            thinking,
          }),
        ),
        repeats,
        concurrency,
        judge_model: judge || undefined,
        use_cache: useCache,
      });
    },
    onSuccess: (runs) => {
      void queryClient.invalidateQueries({ queryKey: ['eval-runs'] });
      toast.success(runs.length > 1 ? `Started ${runs.length} runs` : 'Run started');
      onOpenChange(false);
      if (runs.length === 1) navigate(`/evals/runs/${runs[0].id}`);
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Could not start the run')),
  });

  const update = (i: number, patch: Partial<Variant>) =>
    setVariants((all) => all.map((v, j) => (j === i ? { ...v, ...patch } : v)));

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="New run"
      description="Each variant runs every case. Re-running the same variant is served from the cache unless you turn it off."
      className="max-w-2xl"
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => start.mutate()} loading={start.isPending} disabled={variants.some((v) => !v.model)}>
            Start {variants.length > 1 ? `${variants.length} runs` : 'run'}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <div className="space-y-3">
          {variants.map((v, i) => (
            <div key={i} className="flex items-end gap-2">
              <Field label={variants.length > 1 ? `Model ${i + 1}` : 'Model'} className="flex-1">
                <ModelPicker value={v.model} onChange={(m) => update(i, { model: m.id })} />
              </Field>
              <Field label="Temp." htmlFor={`temp-${i}`} className="w-24">
                <Input
                  id={`temp-${i}`}
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
                  value={v.temperature}
                  onChange={(e) => update(i, { temperature: e.target.value })}
                />
              </Field>
              {variants.length > 1 && (
                <Button variant="ghost" size="icon" aria-label="Remove variant" onClick={() => setVariants((all) => all.filter((_, j) => j !== i))}>
                  <X size={16} />
                </Button>
              )}
            </div>
          ))}
          {variants.length < 10 && (
            <Button variant="ghost" size="sm" onClick={() => setVariants((all) => [...all, { model: '', temperature: '0' }])}>
              <Plus size={14} /> Add a variant to compare
            </Button>
          )}
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Repeats" htmlFor="run-repeats" hint="Run each case N times to measure flakiness">
            <Input id="run-repeats" type="number" min={1} max={20} value={repeats} onChange={(e) => setRepeats(Math.max(1, Math.min(20, Number(e.target.value) || 1)))} />
          </Field>
          <Field label="Concurrency" htmlFor="run-concurrency" hint="Parallel requests per run">
            <Input
              id="run-concurrency"
              type="number"
              min={1}
              max={64}
              value={concurrency}
              onChange={(e) => setConcurrency(Math.max(1, Math.min(64, Number(e.target.value) || 1)))}
            />
          </Field>
        </div>
        <Field label="Judge model (for llm_judge assertions)" hint="Defaults to the workspace default model">
          <ModelPicker value={judge} onChange={(m) => setJudge(m.id)} />
        </Field>
        <div className="flex flex-wrap gap-6 text-sm">
          <label className="flex items-center gap-2">
            <Switch checked={thinking} onCheckedChange={setThinking} aria-label="Thinking" /> Let reasoning models think
          </label>
          <label className="flex items-center gap-2">
            <Switch checked={useCache} onCheckedChange={setUseCache} aria-label="Use cache" /> Use response cache
          </label>
        </div>
      </div>
    </Dialog>
  );
};
