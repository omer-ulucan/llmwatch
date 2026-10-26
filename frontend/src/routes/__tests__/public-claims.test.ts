/**
 * The public pages and the README must describe only what the project actually does: no
 * compliance, uptime or savings claims, no made-up usage numbers, and no
 * references to the removed DynamoDB/AWS/LangChain stack.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

// Paths relative to src/routes.
const PAGES = ['home.tsx', 'docs.tsx', '../../../README.md'];

const BANNED: [RegExp, string][] = [
  [/SOC\s?2/i, 'SOC 2 claim'],
  [/\d+(\.\d+)?%\s*(uptime|SLA)/i, 'uptime/SLA claim'],
  [/uptime sla/i, 'uptime/SLA claim'],
  [/by (up to )?\d+%/i, 'savings percentage'],
  [/cost reduction/i, 'savings claim'],
  [/\d+[MK]\+/, 'usage statistic'],
  [/free trial|book a demo|talk to sales/i, 'sales copy for a product that is not sold'],
  [/dynamodb|aws_|langchain/i, 'removed stack'],
];

describe.each(PAGES)('%s', (page) => {
  const source = readFileSync(resolve(__dirname, '..', page), 'utf8');
  it.each(BANNED)('has no %s', (pattern, what) => {
    expect(source.match(pattern)?.[0], what).toBeUndefined();
  });
});
