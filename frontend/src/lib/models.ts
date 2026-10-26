import type { ModelInfo } from '@/types';

/** "$0.15 / $0.60 per 1M" or "unpriced". */
export function priceLabel(model: Pick<ModelInfo, 'input_price_per_mtok' | 'output_price_per_mtok' | 'priced'>): string {
  if (!model.priced) return 'unpriced';
  const fmt = (v: number | null) => (v === null ? '?' : v === 0 ? '0' : `$${v}`);
  if (model.input_price_per_mtok === 0 && model.output_price_per_mtok === 0) return 'free';
  return `${fmt(model.input_price_per_mtok)} / ${fmt(model.output_price_per_mtok)} per 1M`;
}
