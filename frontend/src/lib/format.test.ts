import { describe, expect, it } from 'vitest';
import {
  DASH,
  formatCost,
  formatMs,
  formatRatio,
  formatSigned,
  formatSignedPct,
} from './format';

describe('formatCost', () => {
  it('keeps sub-cent costs visible', () => {
    expect(formatCost(0.000123)).toBe('$0.00012');
    expect(formatCost(0.0042)).toBe('$0.0042');
  });
  it('uses cents precision for larger amounts', () => {
    expect(formatCost(0.0512)).toBe('$0.0512');
    expect(formatCost(12.3456)).toBe('$12.35');
  });
  it('shows zero and missing values honestly', () => {
    expect(formatCost(0)).toBe('$0');
    expect(formatCost(null)).toBe(DASH);
    expect(formatCost(undefined)).toBe(DASH);
  });
});

describe('formatMs', () => {
  it('picks a sensible unit', () => {
    expect(formatMs(812.4)).toBe('812 ms');
    expect(formatMs(1534)).toBe('1.53 s');
    expect(formatMs(34_944)).toBe('34.9 s');
    expect(formatMs(150_000)).toBe('2.5 min');
    expect(formatMs(null)).toBe(DASH);
  });
});

describe('percentages and signs', () => {
  it('formats ratios and signed values', () => {
    expect(formatRatio(0.5512)).toBe('55.1%');
    expect(formatSignedPct(12.34)).toBe('+12.3%');
    expect(formatSignedPct(-4)).toBe('-4.0%');
    expect(formatSigned(0.4)).toBe('+0.400');
    expect(formatSigned(-0.1234, 2)).toBe('-0.12');
    expect(formatRatio(null)).toBe(DASH);
  });
});
