/**
 * Component: AgentTimeline
 * Purpose: Vertical timeline of agent step cards with connecting lines.
 * WHY: Provides a chronological view of the agent's execution flow. The vertical line
 * connecting steps makes the sequential nature of the ReAct loop visually clear.
 * Uses Framer Motion stagger animation as steps stream in from SSE.
 */
import React from 'react';
import AgentStepCard from './AgentStepCard';
import type { AgentEvent } from '@/types';

interface AgentTimelineProps {
  steps: AgentEvent[];
}

const AgentTimeline: React.FC<AgentTimelineProps> = ({ steps }) => {
  // Filter out run_end events (handled by summary card)
  const visibleSteps = steps.filter(s => s.event_type !== 'run_end');

  if (visibleSteps.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
        Agent steps will appear here as the agent executes...
      </div>
    );
  }

  return (
    <div className="relative space-y-3 pl-6">
      {/* Vertical connecting line */}
      <div className="absolute left-[11px] top-2 bottom-2 w-px bg-gradient-to-b from-primary/40 via-primary/20 to-transparent" />

      {visibleSteps.map((step, idx) => (
        <div key={`${step.run_id}-${step.step_index}`} className="relative">
          {/* Timeline dot */}
          <div className="absolute -left-6 top-5 w-[9px] h-[9px] rounded-full bg-primary/60 border-2 border-card ring-2 ring-primary/20" />
          <AgentStepCard event={step} index={idx} />
        </div>
      ))}
    </div>
  );
};

export default AgentTimeline;
