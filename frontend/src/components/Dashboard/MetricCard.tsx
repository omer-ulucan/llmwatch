/**
 * Component: MetricCard
 * Purpose: A standardized widget for displaying a single KPIs with trend data.
 * WHY: Ensures visual consistency across Dashboards and Analytics panels.
 */
import React from 'react';
import { motion } from 'framer-motion';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

interface MetricCardProps {
  title: string;
  value: string | number;
  trend?: number; // percentage
  trendLabel?: string;
  icon: React.ReactNode;
  inverseTrend?: boolean; // If true, up is bad (red) and down is good (green)
  delay?: number;
}

const MetricCard: React.FC<MetricCardProps> = ({ 
  title, value, trend, trendLabel, icon, inverseTrend = false, delay = 0 
}) => {
  
  const isUp = trend !== undefined && trend > 0;
  const isGood = inverseTrend ? !isUp : isUp;
  
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay }}
      whileHover={{ y: -5 }}
      className="glass-card p-6 rounded-2xl relative overflow-hidden group w-full"
    >
      <div className="absolute -right-6 -top-6 w-24 h-24 bg-primary/5 rounded-full blur-2xl group-hover:bg-primary/20 transition-colors duration-500" />
      
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-muted-foreground tracking-wide uppercase">{title}</h3>
        <div className="p-2.5 bg-white/[0.03] rounded-xl text-primary border border-white/[0.02]">
          {icon}
        </div>
      </div>
      
      <div className="flex items-end justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">{value}</h2>
          
          {trend !== undefined && (
            <div className="flex items-center gap-2 mt-2">
              <span className={`flex items-center text-sm font-medium px-1.5 py-0.5 rounded-md ${
                isGood ? 'text-success bg-success-bg' : 'text-error bg-error-bg'
              }`}>
                {isUp ? <ArrowUpRight size={14} className="mr-0.5" /> : <ArrowDownRight size={14} className="mr-0.5" />}
                {Math.abs(trend)}%
              </span>
              {trendLabel && <span className="text-xs text-muted-foreground">{trendLabel}</span>}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
};

export default MetricCard;
