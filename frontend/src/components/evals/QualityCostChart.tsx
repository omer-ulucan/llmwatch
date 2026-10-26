/**
 * Mean score against cost per case, one point per completed run. The frontier is the
 * upper-left: better quality for less money.
 */
import React from 'react';
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts';
import { costPerItem } from '@/lib/evals';
import { formatCost } from '@/lib/format';
import type { EvalRun } from '@/types';

const axis = { stroke: 'var(--color-muted-foreground)', fontSize: 11, tickLine: false, axisLine: false } as const;

interface Point {
  id: string;
  label: string;
  cost: number;
  score: number;
}

export const QualityCostChart: React.FC<{ runs: EvalRun[]; height?: number }> = ({ runs, height = 280 }) => {
  const points: Point[] = runs
    .filter((r) => r.status === 'completed' && r.mean_score !== null)
    .map((r) => ({ id: r.id, label: r.label, cost: costPerItem(r) ?? 0, score: r.mean_score ?? 0 }));
  if (points.length === 0) {
    return <p className="text-sm text-muted-foreground">Complete a run to see quality against cost.</p>;
  }
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer>
        <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.05)" />
          <XAxis type="number" dataKey="cost" name="Cost per case" tickFormatter={(v: number) => formatCost(v)} {...axis} />
          <YAxis type="number" dataKey="score" name="Mean score" domain={[0, 1]} {...axis} width={40} />
          <ZAxis range={[80, 80]} />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            content={({ payload }) => {
              const p = payload?.[0]?.payload as Point | undefined;
              if (!p) return null;
              return (
                <div className="rounded-lg border border-card-border bg-card px-3 py-2 text-xs shadow-lg">
                  <div className="font-medium">{p.label}</div>
                  <div className="text-muted-foreground">
                    score {p.score.toFixed(3)} · {formatCost(p.cost)}/case
                  </div>
                </div>
              );
            }}
          />
          <Scatter data={points} fill="var(--color-primary)" />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
};
