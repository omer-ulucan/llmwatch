import type { EvalRun, RunStatus } from '@/types';

export const isActiveStatus = (status: RunStatus) =>
  status === 'pending' || status === 'running' || status === 'cancelling';

/** Cost per evaluated item for a run (null when nothing ran). */
export function costPerItem(run: Pick<EvalRun, 'total_cost_usd' | 'completed_items'>): number | null {
  return run.completed_items ? run.total_cost_usd / run.completed_items : null;
}

/**
 * Run labels for variants that share a model (otherwise the runs would all be called
 * "Provider/model"); undefined keeps the server's default label.
 */
export function variantLabels(
  variants: { model: string; temperature: string }[],
  nameOf: (modelId: string) => string,
): (string | undefined)[] {
  return variants.map((v) => {
    if (variants.filter((o) => o.model === v.model).length < 2) return undefined;
    return v.temperature === '' ? `${nameOf(v.model)} (default temp.)` : `${nameOf(v.model)} (temp. ${v.temperature})`;
  });
}

export const STARTER_SUITE = `name: my-first-suite
description: What this suite checks
system_prompt: You are a concise assistant.
prompt: |
  Answer with one word: what is the capital of {{ country }}?
cases:
  - id: france
    vars: {country: France}
    assert:
      - {type: contains, value: Paris, case_sensitive: false}
  - id: japan
    vars: {country: Japan}
    assert:
      - {type: contains, value: Tokyo, case_sensitive: false}
`;
