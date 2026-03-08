/**
 * Component: Chat
 * Purpose: Two-pane conversational interface comparing LLMs.
 * WHY: Needs complex state to handle streaming (or pseudo-streaming) and dual model capabilities. 
 * Includes Framer Motion layout animations for the thinking mode expand.
 */
import React, { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Send, Bot, BrainCircuit, Zap, Loader2, Clock } from 'lucide-react';
import { apiClient } from '@/api/client';
import * as Switch from '@radix-ui/react-switch';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  thinking?: string;
  modelUsed?: string;
  latency?: number;
}

const Chat: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [selectedModel, setSelectedModel] = useState<'qwen' | 'gemini'>('qwen');
  const [thinkingMode, setThinkingMode] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  
  const endOfMessagesRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    
    const userMessage: Message = { id: Date.now().toString(), role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const res = await apiClient.post('/chat/completions', {
        prompt: userMessage.content,
        model: selectedModel,
        thinking_mode: thinkingMode
      });
      
      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: res.data.response,
        thinking: res.data.thinking_content,
        modelUsed: res.data.model_used,
        latency: res.data.latency_ms
      };
      setMessages(prev => [...prev, aiMessage]);
    } catch (err: any) {
      console.error(err);
      const detail = err?.response?.data?.error || err?.message || 'Connection to LLM routing engine failed.';
      setMessages(prev => [...prev, { id: 'error', role: 'assistant', content: `Error: ${detail}` }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex bg-background h-[calc(100vh-8rem)] rounded-2xl overflow-hidden glass-card border border-card-border relative z-10">
      
      {/* Left Panel: Configuration */}
      <div className="w-80 border-r border-border bg-card/50 p-6 flex flex-col flex-shrink-0">
        <h3 className="text-lg font-semibold mb-6 flex items-center gap-2">
          <BrainCircuit className="text-primary" />
          Model Routing
        </h3>
        
        <div className="space-y-4 mb-8">
          {/* Model Selection Cards */}
          {(['qwen', 'gemini'] as const).map(m => (
            <button
              key={m}
              onClick={() => setSelectedModel(m)}
              className={`w-full text-left p-4 rounded-xl border transition-all duration-300 relative overflow-hidden group cursor-pointer ${
                selectedModel === m 
                  ? 'bg-primary/10 border-primary glow-effect' 
                  : 'bg-white/[0.02] border-card-border hover:bg-white/[0.05]'
              }`}
            >
              <div className="flex justify-between items-center mb-1">
                <span className="font-semibold capitalize text-foreground">{m === 'qwen' ? 'Qwen3.5-35B' : 'Gemini 3 Flash'}</span>
                <div className={`w-2 h-2 rounded-full ${selectedModel === m ? 'bg-primary shadow-[0_0_8px_rgba(59,130,246,0.8)]' : 'bg-muted-foreground'}`} />
              </div>
              <span className="text-xs text-muted-foreground">{m === 'qwen' ? 'Self-hosted standard' : 'Google API'}</span>
            </button>
          ))}
        </div>

        <div className="flex items-center justify-between p-4 glass-panel rounded-xl">
          <div>
            <span className="block font-medium text-sm">Reasoning Mode</span>
            <span className="text-xs text-muted-foreground ml-0">Enable deep thinking</span>
          </div>
          <Switch.Root
            checked={thinkingMode}
            onCheckedChange={setThinkingMode}
            className={`w-[42px] h-[25px] rounded-full relative shadow-[0_2px_10px] shadow-black/40 cursor-pointer outline-none ${thinkingMode ? 'bg-primary' : 'bg-muted'}`}
          >
            <Switch.Thumb className={`block w-[21px] h-[21px] bg-white rounded-full transition-transform duration-100 translate-x-0.5 will-change-transform ${thinkingMode ? 'translate-x-[19px]' : ''}`} />
          </Switch.Root>
        </div>
        
        <div className="mt-auto p-4 bg-white/[0.02] rounded-xl border border-white/[0.05]">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-2">Session Stats</span>
          <div className="flex justify-between items-center text-sm mb-1">
            <span className="text-muted-foreground">Messages</span>
            <span>{messages.filter(m => m.role === 'user').length}</span>
          </div>
        </div>
      </div>

      {/* Right Panel: Chat Thread */}
      <div className="flex-1 flex flex-col relative w-full overflow-hidden">
        <div className="flex-1 overflow-y-auto overflow-x-hidden p-6 space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-4">
              <Zap size={48} className="text-primary/20" />
              <p>Initialize inference engine.</p>
            </div>
          ) : (
            messages.map((msg) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex gap-4 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role === 'assistant' && (
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${msg.modelUsed === 'qwen' ? 'bg-secondary/20 text-secondary' : 'bg-primary/20 text-primary'}`}>
                    <Bot size={16} />
                  </div>
                )}
                
                <div className={`max-w-[80%] flex flex-col gap-2 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                  <div className={`p-4 rounded-2xl ${msg.role === 'user' ? 'bg-gradient-to-br from-primary to-primary-hover text-white rounded-tr-sm' : 'glass-panel rounded-tl-sm text-foreground overflow-x-auto w-full'}`}>
                    <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                  </div>
                  
                  {msg.role === 'assistant' && (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground pl-2">
                      <span className="uppercase font-semibold tracking-wider">{msg.modelUsed}</span>
                      <span>•</span>
                      <span className="flex items-center gap-1">
                        <Clock size={10} /> {msg.latency?.toFixed(0)}ms
                      </span>
                    </div>
                  )}

                  {msg.thinking && (
                    <details className="w-full mt-2 cursor-pointer group">
                      <summary className="text-xs text-muted-foreground font-medium mb-2 opacity-60 hover:opacity-100 transition-opacity flex items-center gap-2 select-none">
                        <BrainCircuit size={12} /> View Reasoning Trace
                      </summary>
                      <div className="p-3 bg-black/40 rounded-lg text-xs font-mono text-muted-foreground leading-relaxed whitespace-pre-wrap border border-white/5 mx-2 w-full max-w-[calc(100%-1rem)]">
                        {msg.thinking}
                      </div>
                    </details>
                  )}
                </div>
              </motion.div>
            ))
          )}
          
          {isLoading && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-4 mb-4">
               <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center">
                  <Bot size={16} className="text-muted-foreground" />
               </div>
               <div className="glass-panel p-4 rounded-2xl rounded-tl-sm flex items-center gap-2 text-muted-foreground">
                 <Loader2 className="animate-spin" size={16} />
                 <span className="text-sm">Generating reasoning...</span>
               </div>
            </motion.div>
          )}
          <div ref={endOfMessagesRef} />
        </div>
        
        {/* Input Bar */}
        <div className="p-4 bg-background/80 backdrop-blur-md border-t border-border">
          <div className="max-w-4xl mx-auto relative flex items-center">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Ask anything..."
              className="w-full bg-input/50 border border-card-border rounded-xl pl-4 pr-14 py-4 text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 resize-none overflow-hidden h-[56px]"
              rows={1}
            />
            <button
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-2 bg-primary text-white rounded-lg hover:bg-primary-hover disabled:opacity-50 transition-colors shadow-lg cursor-pointer"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Chat;
