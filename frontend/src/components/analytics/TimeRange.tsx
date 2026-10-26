/** Time range selector (state lives in the URL, see useTimeRange). */
import React from 'react';
import { RANGES, type RangeId } from '@/hooks/useTimeRange';
import { cn } from '@/lib/cn';

export const TimeRangePicker: React.FC<{ value: RangeId; onChange: (id: RangeId) => void }> = ({ value, onChange }) => (
  <div className="inline-flex rounded-xl border border-card-border bg-black/20 p-1" role="radiogroup" aria-label="Time range">
    {RANGES.map((r) => (
      <button
        key={r.id}
        type="button"
        role="radio"
        aria-checked={value === r.id}
        onClick={() => onChange(r.id)}
        className={cn(
          'rounded-lg px-3 py-1 text-sm transition-colors cursor-pointer',
          value === r.id ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground',
        )}
      >
        {r.label}
      </button>
    ))}
  </div>
);
