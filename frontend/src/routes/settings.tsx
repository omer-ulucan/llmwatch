/**
 * Component: Settings
 * Purpose: Manage tenant configurations.
 * WHY: Standard UI requirement for API key management and danger zones.
 */
import React from 'react';
import { Save, AlertTriangle } from 'lucide-react';

const Settings: React.FC = () => {
  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-12">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Organization Settings</h1>
        <p className="text-muted-foreground">Manage your workspace profiles and billing limits.</p>
      </div>

      <div className="glass-panel rounded-2xl p-8 space-y-6">
        <h2 className="text-lg font-semibold border-b border-card-border pb-4">API Configuration</h2>
        
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium text-muted-foreground mb-1 block">Root API Key</label>
            <div className="flex gap-4">
              <input 
                type="password" 
                value="llmw_sk_948f2940afb12x91204018..." 
                readOnly
                className="flex-1 bg-input/50 border border-card-border rounded-xl px-4 py-2 text-foreground font-mono focus:outline-none"
              />
              <button className="px-6 bg-white/[0.05] hover:bg-white/[0.1] rounded-xl border border-card-border transition-colors cursor-pointer text-sm font-medium hover:text-white">
                Regenerate
              </button>
            </div>
          </div>
        </div>
        
        <div className="pt-4">
          <button className="flex items-center gap-2 bg-primary text-white px-6 py-2.5 rounded-xl hover:bg-primary-hover shadow-[0_0_20px_rgba(59,130,246,0.2)] hover:shadow-[0_0_30px_rgba(59,130,246,0.4)] transition-all font-medium cursor-pointer">
            <Save size={16} /> Save Changes
          </button>
        </div>
      </div>

      <div className="border border-error/30 bg-error/5 rounded-2xl p-8 space-y-4 relative overflow-hidden group hover:bg-error/10 transition-colors">
        <div className="absolute top-0 right-0 w-64 h-64 bg-error/10 rounded-full blur-3xl translate-x-1/2 -translate-y-1/2" />
        <h2 className="text-lg font-semibold text-error flex items-center gap-2">
          <AlertTriangle size={20} /> Danger Zone
        </h2>
        <p className="text-sm text-foreground/80">
          Permanently delete this workspace and all associated logs. This action cannot be reversed.
        </p>
        <button className="bg-error text-white px-6 py-2.5 rounded-xl hover:bg-error/90 font-medium transition-colors cursor-pointer relative z-10 shadow-lg shadow-error/20">
          Delete Workspace
        </button>
      </div>
    </div>
  );
};

export default Settings;
