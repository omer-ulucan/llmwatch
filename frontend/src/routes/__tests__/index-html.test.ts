import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('index.html', () => {
  const html = readFileSync(resolve(__dirname, '../../../index.html'), 'utf8');

  it('declares an icon, so browsers do not request a missing /favicon.ico', () => {
    expect(html).toMatch(/<link[^>]+rel="icon"/);
  });
});
