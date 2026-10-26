import { describe, expect, it } from 'vitest';
import { parse } from 'yaml';
import { STARTER_SUITE, costPerItem, isActiveStatus, variantLabels } from './evals';

describe('eval helpers', () => {
  it('treats pending, running and cancelling as active', () => {
    expect(['pending', 'running', 'cancelling'].every((s) => isActiveStatus(s as never))).toBe(true);
    expect(['completed', 'failed', 'cancelled', 'interrupted'].some((s) => isActiveStatus(s as never))).toBe(false);
  });

  it('computes cost per completed item', () => {
    expect(costPerItem({ total_cost_usd: 0.3, completed_items: 3 })).toBeCloseTo(0.1);
    expect(costPerItem({ total_cost_usd: 0, completed_items: 0 })).toBeNull();
  });

  it('ships a starter suite with the required fields', () => {
    const doc = parse(STARTER_SUITE) as { name: string; prompt: string; cases: { id: string; vars: object }[] };
    expect(doc.name).toBeTruthy();
    expect(doc.prompt).toContain('{{ country }}');
    expect(doc.cases.length).toBeGreaterThan(0);
    expect(doc.cases.every((c) => c.id && c.vars)).toBe(true);
  });

  it('labels only variants that share a model', () => {
    const name = (id: string) => (id === 'a' ? 'Ollama/qwen' : 'OpenAI/gpt');
    expect(
      variantLabels(
        [
          { model: 'a', temperature: '0' },
          { model: 'a', temperature: '1' },
          { model: 'b', temperature: '0' },
        ],
        name,
      ),
    ).toEqual(['Ollama/qwen (temp. 0)', 'Ollama/qwen (temp. 1)', undefined]);
    expect(variantLabels([{ model: 'a', temperature: '' }, { model: 'a', temperature: '' }], name)[0]).toBe(
      'Ollama/qwen (default temp.)',
    );
  });
});
