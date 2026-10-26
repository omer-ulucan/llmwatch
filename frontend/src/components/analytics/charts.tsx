/**
 * Small time-series charts on Recharts, styled with the theme tokens.
 */
import React from 'react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { TimeseriesBucket } from '@/types';

const axis = { stroke: 'var(--color-muted-foreground)', fontSize: 11, tickLine: false, axisLine: false } as const;

function tickFormatter(bucketSeconds: number) {
  return (iso: string) => {
    const d = new Date(iso);
    return bucketSeconds >= 86400
      ? d.toLocaleDateString([], { month: 'short', day: 'numeric' })
      : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };
}

interface SeriesChartProps {
  buckets: TimeseriesBucket[];
  bucketSeconds: number;
  series: { key: keyof TimeseriesBucket; label: string; color: string }[];
  valueFormatter?: (v: number) => string;
  height?: number;
}

export const SeriesChart: React.FC<SeriesChartProps> = ({ buckets, bucketSeconds, series, valueFormatter, height = 240 }) => {
  const fmt = tickFormatter(bucketSeconds);
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={buckets} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            {series.map((s) => (
              <linearGradient key={s.key} id={`grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={s.color} stopOpacity={0.35} />
                <stop offset="95%" stopColor={s.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
          <XAxis dataKey="ts" tickFormatter={fmt} minTickGap={32} {...axis} />
          <YAxis width={56} tickFormatter={valueFormatter} {...axis} />
          <Tooltip
            labelFormatter={(l) => new Date(String(l)).toLocaleString()}
            formatter={(v, name) => [valueFormatter ? valueFormatter(Number(v)) : String(v), name]}
            contentStyle={{
              background: 'var(--color-card)',
              border: '1px solid var(--color-card-border)',
              borderRadius: 12,
              fontSize: 12,
            }}
          />
          {series.map((s) => (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              strokeWidth={2}
              fill={`url(#grad-${s.key})`}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};
