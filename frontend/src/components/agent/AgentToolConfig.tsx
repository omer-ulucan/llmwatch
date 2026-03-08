/**
 * Component: AgentToolConfig
 * Purpose: Tool selection checkboxes with descriptions.
 * WHY: Lets the user control which tools the agent has access to before running.
 * This maps directly to the `tools` field in the AgentRunRequest schema.
 */
import React from 'react';
import { Search, Code, Database, FileText } from 'lucide-react';

interface ToolOption {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
}

const TOOLS: ToolOption[] = [
  { id: 'web_search', name: 'Web Search', description: 'Search the web via DuckDuckGo', icon: <Search size={16} /> },
  { id: 'code_execute', name: 'Code Execute', description: 'Run Python code in sandbox', icon: <Code size={16} /> },
  { id: 'db_query', name: 'DB Query', description: 'Query your LLM usage logs', icon: <Database size={16} /> },
  { id: 'doc_analyze', name: 'Doc Analyze', description: 'Fetch & analyze a URL', icon: <FileText size={16} /> },
];

interface AgentToolConfigProps {
  selectedTools: string[];
  onChange: (tools: string[]) => void;
}

const AgentToolConfig: React.FC<AgentToolConfigProps> = ({ selectedTools, onChange }) => {
  const toggle = (toolId: string) => {
    if (selectedTools.includes(toolId)) {
      onChange(selectedTools.filter(t => t !== toolId));
    } else {
      onChange([...selectedTools, toolId]);
    }
  };

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
        Agent Tools
      </h4>
      {TOOLS.map((tool) => {
        const isActive = selectedTools.includes(tool.id);
        return (
          <button
            key={tool.id}
            onClick={() => toggle(tool.id)}
            className={`w-full text-left p-3 rounded-lg border transition-all duration-200 flex items-center gap-3 cursor-pointer ${
              isActive
                ? 'bg-primary/10 border-primary/30 text-foreground'
                : 'bg-white/[0.02] border-card-border text-muted-foreground hover:bg-white/[0.05]'
            }`}
          >
            <div className={`p-1.5 rounded-md ${isActive ? 'bg-primary/20 text-primary' : 'bg-white/5'}`}>
              {tool.icon}
            </div>
            <div className="flex-1 min-w-0">
              <span className="text-sm font-medium block">{tool.name}</span>
              <span className="text-xs text-muted-foreground">{tool.description}</span>
            </div>
            <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-colors ${
              isActive ? 'bg-primary border-primary' : 'border-muted-foreground/40'
            }`}>
              {isActive && (
                <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                  <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
};

export default AgentToolConfig;
