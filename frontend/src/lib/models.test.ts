import { describe, expect, it } from 'vitest';
import { priceLabel } from './models';

describe('priceLabel', () => {
  it('says unpriced instead of $0 when no price is set', () => {
    expect(priceLabel({ priced: false, input_price_per_mtok: null, output_price_per_mtok: null })).toBe('unpriced');
  });
  it('labels free local models', () => {
    expect(priceLabel({ priced: true, input_price_per_mtok: 0, output_price_per_mtok: 0 })).toBe('free');
  });
  it('shows input / output per 1M', () => {
    expect(priceLabel({ priced: true, input_price_per_mtok: 0.5, output_price_per_mtok: 3 })).toBe('$0.5 / $3 per 1M');
    expect(priceLabel({ priced: true, input_price_per_mtok: 1, output_price_per_mtok: null })).toBe('$1 / ? per 1M');
  });
});
