/**
 * Component: Dashboard
 * Purpose: Main analytical hub.
 * WHY: Recharts powers the visual metrics. The data is staggered via Framer motion for a dynamic feel.
 */
import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, DollarSign, Clock, AlertTriangle } from 'lucide-react';
import MetricCard from '@/components/Dashboard/MetricCard';
import { apiClient } from '@/api/client';
import { MetricSummary } from '@/types';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
  BarChart, Bar, Legend
} from 'recharts';

// Mock timeseries logic since true timeseries requires polling
const mockTimeseries = Array.from({ length: 24 }).map((_, i) => ({
  time: `${i}:00`,
  cost: Math.random() * 10 + 2,
  latency: Math.random() * 300 + 400
}));

const Dashboard: React.FC = () => {
  const [summary, setSummary] = useState<MetricSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // WHY: Initial data fetch to hydrate dashboard KPIs
    apiClient.get('/analytics/summary')
      .then(res => setSummary(res.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-8 h-8 rounded-full border-t-2 border-primary animate-spin" />
      </div>
    );
  }

  const comparisonData = summary ? [
    { name: 'Requests', Qwen: summary.model_breakdown.qwen.requests, Gemini: summary.model_breakdown.gemini.requests },
    { name: 'Cost ($)', Qwen: Number(summary.model_breakdown.qwen.cost.toFixed(4)), Gemini: Number(summary.model_breakdown.gemini.cost.toFixed(4)) },
  ] : [];

  return (
    <div className="max-w-7xl mx-auto space-y-8 pb-12">
      {/* Top Level KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard 
          title="Total Requests (24h)" 
          value={(summary?.total_requests || 0).toLocaleString()} 
          trend={12.5} 
          icon={<Activity size={24} />} 
          delay={0.1}
        />
        <MetricCard 
          title="Total Cost" 
          value={`$${(summary?.total_cost_usd || 0).toFixed(4)}`} 
          trend={-2.4} 
          inverseTrend
          icon={<DollarSign size={24} />} 
          delay={0.2}
        />
        <MetricCard 
          title="Avg Latency" 
          value={`${Math.round(summary?.avg_latency_ms || 0)}ms`} 
          trend={-15} 
          inverseTrend
          icon={<Clock size={24} />} 
          delay={0.3}
        />
        <MetricCard 
          title="Error Rate" 
          value={`${(summary?.error_rate_pct || 0).toFixed(1)}%`} 
          trend={0} 
          inverseTrend
          icon={<AlertTriangle size={24} />} 
          delay={0.4}
        />
      </div>

      {/* Main Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="col-span-1 lg:col-span-2 glass-panel p-6 rounded-2xl h-[400px] flex flex-col"
        >
          <h3 className="text-lg font-semibold mb-6 tracking-tight">Cost & Activity Over Time</h3>
          <div className="flex-1 min-h-0 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={mockTimeseries}>
                <defs>
                  <linearGradient id="colorCost" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--color-primary)" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="var(--color-primary)" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="time" stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                <RechartsTooltip 
                  contentStyle={{ backgroundColor: 'var(--color-card)', borderColor: 'var(--color-card-border)', borderRadius: '12px' }}
                  itemStyle={{ color: 'var(--color-foreground)' }}
                />
                <Area type="monotone" dataKey="cost" stroke="var(--color-primary)" strokeWidth={3} fillOpacity={1} fill="url(#colorCost)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </motion.div>

        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
          className="col-span-1 glass-panel p-6 rounded-2xl h-[400px] flex flex-col"
        >
          <h3 className="text-lg font-semibold mb-6 tracking-tight">Model Distribution</h3>
          <div className="flex-1 min-h-0 w-full">
             <ResponsiveContainer width="100%" height="100%">
              <BarChart data={comparisonData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="name" stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                <RechartsTooltip 
                   cursor={{fill: 'rgba(255,255,255,0.02)'}}
                   contentStyle={{ backgroundColor: 'var(--color-card)', borderColor: 'var(--color-card-border)', borderRadius: '12px' }}
                />
                <Legend iconType="circle" />
                <Bar dataKey="Qwen" fill="var(--color-secondary)" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Gemini" fill="var(--color-primary)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </motion.div>
      </div>
    </div>
  );
};

export default Dashboard;
