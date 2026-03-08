/**
 * Component: Analytics
 * Purpose: Advanced metric visualization.
 * WHY: Needs a sortable table for raw logs allowing engineers to find specific edge cases.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Download, Search } from 'lucide-react';
import { apiClient } from '@/api/client';
import { LogEntry } from '@/types';
import { format } from 'date-fns';

const Analytics: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [search, setSearch] = useState('');
  
  useEffect(() => {
    apiClient.get('/analytics/logs?limit=100').then(res => setLogs(res.data)).catch(console.error);
  }, []);

  const filteredLogs = logs.filter(log => 
    log.prompt_preview.toLowerCase().includes(search.toLowerCase()) || 
    log.error_type?.toLowerCase().includes(search.toLowerCase())
  );

  const handleExportCSV = useCallback(() => {
    if (filteredLogs.length === 0) {
      window.alert('No data to export.');
      return;
    }

    const headers = ['Timestamp', 'Model', 'Prompt Preview', 'Latency (ms)', 'Cost (USD)', 'Status'];
    const rows = filteredLogs.map(log => [
      log.timestamp,
      log.model_name,
      `"${(log.prompt_preview || '').replace(/"/g, '""')}"`,
      Math.round(log.latency_ms).toString(),
      log.cost_usd.toFixed(5),
      log.success ? 'Success' : 'Error',
    ]);
    
    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `llmwatch-logs-${format(new Date(), 'yyyy-MM-dd')}.csv`);
    link.click();
    URL.revokeObjectURL(url);
  }, [filteredLogs]);

  return (
    <div className="max-w-7xl mx-auto pb-12">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight mb-1">Analytics Explorer</h1>
          <p className="text-muted-foreground">Inspect raw invocation traces across all deployed models.</p>
        </div>
        <button 
          onClick={handleExportCSV}
          className="flex items-center gap-2 px-4 py-2 glass-card rounded-lg hover:bg-white/[0.05] transition-colors cursor-pointer text-sm font-medium hover:text-white"
        >
          <Download size={16} /> Export CSV
        </button>
      </div>

      <div className="glass-panel rounded-2xl overflow-hidden flex flex-col min-h-[500px]">
        <div className="p-4 border-b border-card-border flex items-center justify-between bg-card/30">
          <div className="relative w-64 max-w-full">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input 
              type="text" 
              placeholder="Search prompts..." 
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full bg-input/50 border border-card-border rounded-lg pl-9 pr-4 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>
        
        <div className="overflow-x-auto flex-1">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-muted-foreground uppercase bg-black/20">
              <tr>
                <th className="px-6 py-4 font-medium whitespace-nowrap">Timestamp</th>
                <th className="px-6 py-4 font-medium">Model</th>
                <th className="px-6 py-4 font-medium">Prompt Preview</th>
                <th className="px-6 py-4 font-medium text-right whitespace-nowrap">Latency</th>
                <th className="px-6 py-4 font-medium text-right">Cost</th>
                <th className="px-6 py-4 font-medium text-center">Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredLogs.map(log => (
                <tr key={log.log_id} className="border-b border-card-border/50 hover:bg-white/[0.02] transition-colors">
                  <td className="px-6 py-4 text-muted-foreground whitespace-nowrap">
                    {format(new Date(log.timestamp), 'MMM d, HH:mm:ss')}
                  </td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 rounded-md text-xs font-semibold uppercase tracking-wider ${log.model_name === 'qwen' ? 'bg-secondary/20 text-secondary' : 'bg-primary/20 text-primary'}`}>
                      {log.model_name}
                    </span>
                  </td>
                  <td className="px-6 py-4 max-w-xs truncate text-foreground">
                    {log.prompt_preview || 'No prompt logged...'}
                  </td>
                  <td className="px-6 py-4 text-right tabular-nums">
                    {Math.round(log.latency_ms)}ms
                  </td>
                  <td className="px-6 py-4 text-right tabular-nums text-muted-foreground">
                    ${log.cost_usd.toFixed(5)}
                  </td>
                  <td className="px-6 py-4 text-center">
                    <div className={`w-2 h-2 rounded-full mx-auto ${log.success ? 'bg-success glow-effect shadow-success/50' : 'bg-error'}`} />
                  </td>
                </tr>
              ))}
              {filteredLogs.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-muted-foreground">
                    No traces found matching criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Analytics;
