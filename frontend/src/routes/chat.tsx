/**
 * Component: Chat
 * Purpose: Chat with any configured model, streamed, with Markdown rendering.
 * WHY: The quickest way to try a model and see what a call costs. Answers stream in
 * as they are generated (or arrive whole with streaming off), reasoning is shown when
 * the provider returns it, and every reply shows latency, tokens and cost.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Bot, BrainCircuit, ChevronDown, Eraser, Send, SlidersHorizontal, Square } from 'lucide-react';
import { apiClient } from '@/api/client';
import { getErrorMessage } from '@/api/errors';
import { Markdown } from '@/components/chat/Markdown';
import { ModelPicker } from '@/components/models/ModelPicker';
import { Button, EmptyState, Field, Input, Sheet, Switch, Textarea } from '@/components/ui';
import { useAvailableModels, useInitialModel } from '@/hooks/useModels';
import { formatCost, formatMs, formatNumber } from '@/lib/format';
import { postSSE } from '@/lib/sse';
import type { ChatMessage, ChatRequest, ChatStreamEvent } from '@/types';

interface Turn {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  model?: string;
  latencyMs?: number;
  inputTokens?: number;
  outputTokens?: number;
  costUsd?: number;
  priced?: boolean;
  error?: string;
  streaming?: boolean;
}

interface ChatSettings {
  model: string;
  thinking: boolean;
  stream: boolean;
  temperature: string;
  maxTokens: string;
  systemPrompt: string;
}

/** How many earlier turns go along as context. */
const HISTORY_TURNS = 20;

let nextId = 0;
const newId = () => `${Date.now()}-${nextId++}`;

const SettingsPanel: React.FC<{ settings: ChatSettings; onChange: (s: ChatSettings) => void }> = ({
  settings,
  onChange,
}) => {
  const set = <K extends keyof ChatSettings>(key: K, value: ChatSettings[K]) => onChange({ ...settings, [key]: value });
  return (
    <div className="space-y-5">
      <Field label="Model" htmlFor="chat-model">
        <ModelPicker id="chat-model" value={settings.model} onChange={(m) => set('model', m.id)} />
      </Field>
      <div className="flex items-center justify-between gap-3">
        <label htmlFor="chat-thinking" className="text-sm">
          <span className="font-medium">Thinking</span>
          <span className="block text-xs text-muted-foreground">Let reasoning models reason first</span>
        </label>
        <Switch id="chat-thinking" checked={settings.thinking} onCheckedChange={(v) => set('thinking', v)} />
      </div>
      <div className="flex items-center justify-between gap-3">
        <label htmlFor="chat-stream" className="text-sm">
          <span className="font-medium">Stream</span>
          <span className="block text-xs text-muted-foreground">Show the answer as it's generated</span>
        </label>
        <Switch id="chat-stream" checked={settings.stream} onCheckedChange={(v) => set('stream', v)} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Temperature" htmlFor="chat-temp">
          <Input
            id="chat-temp"
            type="number"
            min={0}
            max={2}
            step={0.1}
            placeholder="default"
            value={settings.temperature}
            onChange={(e) => set('temperature', e.target.value)}
          />
        </Field>
        <Field label="Max tokens" htmlFor="chat-max">
          <Input
            id="chat-max"
            type="number"
            min={1}
            placeholder="default"
            value={settings.maxTokens}
            onChange={(e) => set('maxTokens', e.target.value)}
          />
        </Field>
      </div>
      <Field label="System prompt" htmlFor="chat-system">
        <Textarea
          id="chat-system"
          rows={4}
          placeholder="Optional instructions for the model"
          value={settings.systemPrompt}
          onChange={(e) => set('systemPrompt', e.target.value)}
        />
      </Field>
    </div>
  );
};

const TurnView: React.FC<{ turn: Turn }> = ({ turn }) => {
  if (turn.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-tr-sm border border-primary/20 bg-primary/10 px-4 py-3 text-[15px]">
          {turn.content}
        </div>
      </div>
    );
  }
  const tokens = (turn.inputTokens ?? 0) + (turn.outputTokens ?? 0);
  return (
    <div className="flex gap-3">
      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary/20 text-secondary">
        <Bot size={16} aria-hidden />
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        {turn.reasoning && (
          <details className="rounded-xl border border-secondary/20 bg-secondary/[0.06] px-3 py-2 text-sm">
            <summary className="flex cursor-pointer items-center gap-2 text-secondary">
              <BrainCircuit size={14} /> Reasoning
              <ChevronDown size={14} className="ml-auto" />
            </summary>
            <div className="mt-2 whitespace-pre-wrap text-muted-foreground">{turn.reasoning}</div>
          </details>
        )}
        <div className="rounded-2xl rounded-tl-sm border border-card-border bg-card/60 px-4 py-3">
          {turn.error ? (
            <p className="text-sm text-error" role="alert">
              {turn.error}
            </p>
          ) : turn.content ? (
            <Markdown>{turn.content}</Markdown>
          ) : turn.streaming ? (
            <span className="inline-flex gap-1" aria-label="Waiting for the model">
              {[0, 1, 2].map((i) => (
                <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-muted-foreground" style={{ animationDelay: `${i * 150}ms` }} />
              ))}
            </span>
          ) : (
            <p className="text-sm text-muted-foreground">(empty response)</p>
          )}
        </div>
        {!turn.streaming && !turn.error && turn.model && (
          <div className="flex flex-wrap gap-x-3 gap-y-1 px-1 text-xs text-muted-foreground">
            <span>{turn.model}</span>
            <span>{formatMs(turn.latencyMs)}</span>
            {tokens > 0 && <span>{formatNumber(tokens)} tokens</span>}
            <span>{turn.priced === false ? 'unpriced' : formatCost(turn.costUsd)}</span>
          </div>
        )}
      </div>
    </div>
  );
};

const Chat: React.FC = () => {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState<ChatSettings>({
    model: '',
    thinking: false,
    stream: true,
    temperature: '',
    maxTokens: '',
    systemPrompt: '',
  });
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const { models, isLoading: modelsLoading } = useAvailableModels();

  const setModel = useCallback((id: string) => setSettings((s) => ({ ...s, model: id })), []);
  useInitialModel(settings.model, setModel);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const patchTurn = (id: string, patch: (t: Turn) => Partial<Turn>) =>
    setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...patch(t) } : t)));

  const send = async () => {
    const prompt = input.trim();
    if (!prompt || busy || !settings.model) return;
    const history: ChatMessage[] = turns
      .filter((t) => !t.error && t.content)
      .slice(-HISTORY_TURNS)
      .map((t) => ({ role: t.role, content: t.content }));
    const request: ChatRequest = {
      model: settings.model,
      prompt,
      messages: history.length ? history : undefined,
      system_prompt: settings.systemPrompt.trim() || undefined,
      thinking_mode: settings.thinking,
      temperature: settings.temperature === '' ? undefined : Number(settings.temperature),
      max_tokens: settings.maxTokens === '' ? undefined : Number(settings.maxTokens),
    };
    const replyId = newId();
    setTurns((all) => [
      ...all,
      { id: newId(), role: 'user', content: prompt },
      { id: replyId, role: 'assistant', content: '', streaming: true },
    ]);
    setInput('');
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      if (settings.stream) {
        await postSSE<ChatStreamEvent>(
          '/chat/stream',
          request,
          (event) => {
            switch (event.type) {
              case 'start':
                patchTurn(replyId, () => ({ model: event.model_used }));
                break;
              case 'delta':
                patchTurn(replyId, (t) => ({ content: t.content + event.text }));
                break;
              case 'reasoning':
                patchTurn(replyId, (t) => ({ reasoning: (t.reasoning ?? '') + event.text }));
                break;
              case 'usage':
                patchTurn(replyId, () => ({ inputTokens: event.input_tokens, outputTokens: event.output_tokens }));
                break;
              case 'error':
                patchTurn(replyId, () => ({ error: `${event.error_type}: ${event.message}` }));
                break;
              case 'done':
                patchTurn(replyId, () => ({ latencyMs: event.latency_ms, costUsd: event.cost_usd, priced: event.priced }));
                break;
            }
          },
          controller.signal,
        );
      } else {
        const { data } = await apiClient.post<{
          response: string;
          thinking_content: string | null;
          latency_ms: number;
          input_tokens: number;
          output_tokens: number;
          cost_usd: number;
          priced: boolean;
          model_used: string;
        }>('/chat/completions', request, { signal: controller.signal });
        patchTurn(replyId, () => ({
          content: data.response,
          reasoning: data.thinking_content ?? undefined,
          latencyMs: data.latency_ms,
          inputTokens: data.input_tokens,
          outputTokens: data.output_tokens,
          costUsd: data.cost_usd,
          priced: data.priced,
          model: data.model_used,
        }));
      }
    } catch (err) {
      if (controller.signal.aborted) {
        patchTurn(replyId, (t) => ({ error: t.content ? undefined : 'Stopped.' }));
      } else {
        patchTurn(replyId, () => ({ error: getErrorMessage(err, 'The request failed') }));
      }
    } finally {
      patchTurn(replyId, () => ({ streaming: false }));
      setBusy(false);
      abortRef.current = null;
    }
  };

  const noModels = !modelsLoading && models.length === 0;

  return (
    <div className="-m-4 flex h-[calc(100%+2rem)] sm:-m-6 sm:h-[calc(100%+3rem)] lg:-m-8 lg:h-[calc(100%+4rem)]">
      <aside className="hidden w-80 shrink-0 overflow-y-auto border-r border-border bg-card/40 p-6 lg:block">
        <h2 className="mb-5 text-sm font-semibold uppercase tracking-wider text-muted-foreground">Settings</h2>
        <SettingsPanel settings={settings} onChange={setSettings} />
      </aside>
      <Sheet open={settingsOpen} onOpenChange={setSettingsOpen} title="Chat settings">
        <SettingsPanel settings={settings} onChange={setSettings} />
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2 sm:px-6">
          <Button variant="ghost" size="sm" className="lg:hidden" onClick={() => setSettingsOpen(true)}>
            <SlidersHorizontal size={16} /> Settings
          </Button>
          <div className="flex-1" />
          <Button variant="ghost" size="sm" onClick={() => setTurns([])} disabled={busy || turns.length === 0}>
            <Eraser size={16} /> Clear
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6" aria-live="polite">
          <div className="mx-auto max-w-3xl space-y-6">
            {turns.length === 0 && (
              <EmptyState
                icon={<Bot size={28} />}
                title={noModels ? 'No models yet' : 'Start a conversation'}
                description={
                  noModels
                    ? 'Add a provider on the Models page to start chatting.'
                    : 'Every reply shows its latency, tokens and cost, and is logged to Analytics.'
                }
              />
            )}
            {turns.map((t) => (
              <TurnView key={t.id} turn={t} />
            ))}
            <div ref={endRef} />
          </div>
        </div>

        <form
          className="border-t border-border p-3 sm:p-4"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <div className="mx-auto flex max-w-3xl items-end gap-2">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              rows={1}
              placeholder={noModels ? 'Add a model first' : 'Message… (Shift+Enter for a new line)'}
              aria-label="Message"
              className="max-h-48 min-h-12 flex-1 resize-none py-3"
              disabled={noModels}
            />
            {busy ? (
              <Button variant="secondary" size="lg" onClick={() => abortRef.current?.abort()} aria-label="Stop">
                <Square size={16} />
              </Button>
            ) : (
              <Button type="submit" size="lg" disabled={!input.trim() || !settings.model} aria-label="Send">
                <Send size={16} />
              </Button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
};

export default Chat;
