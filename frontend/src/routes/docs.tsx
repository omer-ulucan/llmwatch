/**
 * Component: Docs
 * Purpose: Public reference for running LLMWatch and calling its API.
 * WHY: Covers what a self-hoster needs on one page: setup, providers, auth, chat,
 * agent, evals, analytics, every endpoint and every setting. The backend also serves
 * its interactive OpenAPI docs at /docs.
 */
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router';
import {
  ArrowLeft,
  BarChart3,
  Book,
  Bot,
  Check,
  ChevronRight,
  Copy,
  FlaskConical,
  Hash,
  Key,
  Menu,
  MessageSquare,
  Network,
  Search,
  Settings,
  Terminal,
  X,
  Zap,
} from 'lucide-react';

/* ── Types ─────────────────────────────────────────────────── */

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  children: { id: string; label: string }[];
}

/* ── Sidebar navigation structure ──────────────────────────── */

const navItems: NavItem[] = [
  {
    id: 'getting-started',
    label: 'Getting started',
    icon: <Book size={16} />,
    children: [
      { id: 'quickstart', label: 'Quickstart' },
      { id: 'local-dev', label: 'Local development' },
      { id: 'demo-mode', label: 'Demo mode' },
    ],
  },
  {
    id: 'providers',
    label: 'Providers & models',
    icon: <Network size={16} />,
    children: [
      { id: 'providers-presets', label: 'Providers' },
      { id: 'providers-ollama', label: 'Ollama and local models' },
      { id: 'models-refs', label: 'Model references' },
      { id: 'models-pricing', label: 'Pricing and cost' },
    ],
  },
  {
    id: 'authentication',
    label: 'Authentication',
    icon: <Key size={16} />,
    children: [
      { id: 'auth-session', label: 'Accounts and sessions' },
      { id: 'auth-api-keys', label: 'API keys' },
    ],
  },
  {
    id: 'chat',
    label: 'Chat',
    icon: <MessageSquare size={16} />,
    children: [
      { id: 'chat-completions', label: 'Completions' },
      { id: 'chat-stream', label: 'Streaming' },
    ],
  },
  {
    id: 'agent',
    label: 'Agent & traces',
    icon: <Bot size={16} />,
    children: [
      { id: 'agent-run', label: 'Run the agent' },
      { id: 'agent-tools', label: 'Tools' },
      { id: 'agent-events', label: 'Events and traces' },
    ],
  },
  {
    id: 'evals',
    label: 'Evals',
    icon: <FlaskConical size={16} />,
    children: [
      { id: 'evals-suites', label: 'Suite format' },
      { id: 'evals-evaluators', label: 'Evaluators' },
      { id: 'evals-runs', label: 'Runs' },
      { id: 'evals-compare', label: 'Comparisons' },
      { id: 'evals-cli', label: 'CLI and CI' },
    ],
  },
  {
    id: 'analytics',
    label: 'Analytics',
    icon: <BarChart3 size={16} />,
    children: [{ id: 'analytics-endpoints', label: 'Endpoints' }],
  },
  {
    id: 'reference',
    label: 'Reference',
    icon: <Terminal size={16} />,
    children: [
      { id: 'api-endpoints', label: 'All endpoints' },
      { id: 'config-env', label: 'Configuration' },
      { id: 'errors', label: 'Errors' },
    ],
  },
];

/* ── Content data ──────────────────────────────────────────── */

const ENDPOINTS: [string, string, string][] = [
  ['GET', '/health', 'Liveness check (no auth)'],
  ['POST', '/auth/register', 'Create a workspace and its owner (when ALLOW_SIGNUP is on)'],
  ['POST', '/auth/login', 'Exchange email and password for a JWT'],
  ['GET', '/auth/me', 'The current user, workspace and role'],
  ['GET', '/workspaces/current', 'The current workspace'],
  ['DELETE', '/workspaces/current', 'Delete the workspace and everything in it (owner only)'],
  ['GET', '/api-keys', 'List API keys'],
  ['POST', '/api-keys', 'Create an API key (shown once)'],
  ['POST', '/api-keys/{key_id}/regenerate', 'Revoke a key and issue a new one'],
  ['DELETE', '/api-keys/{key_id}', 'Revoke a key'],
  ['GET', '/providers/presets', 'Provider presets with default base URLs'],
  ['GET', '/providers', 'List providers (keys masked)'],
  ['POST', '/providers', 'Add a provider'],
  ['GET', '/providers/{id}', 'Get a provider'],
  ['PATCH', '/providers/{id}', 'Update a provider'],
  ['DELETE', '/providers/{id}', 'Delete a provider and its models'],
  ['POST', '/providers/{id}/test', 'Check the connection and list models'],
  ['POST', '/providers/{id}/discover', 'Import the models the provider lists'],
  ['GET', '/models', 'Models grouped by provider'],
  ['POST', '/models', 'Add a model'],
  ['GET', '/models/resolve', 'What a model reference points to'],
  ['PATCH', '/models/{id}', 'Update prices, capabilities, default'],
  ['DELETE', '/models/{id}', 'Delete a model'],
  ['POST', '/chat/completions', 'One completion'],
  ['POST', '/chat/stream', 'A streamed completion (SSE)'],
  ['POST', '/agent/run', 'Run the agent (SSE)'],
  ['POST', '/agent/runs/{run_id}/cancel', 'Cancel a running agent run'],
  ['GET', '/agent/tools', 'Tools this server allows'],
  ['GET', '/agent/traces', 'Recent agent traces'],
  ['GET', '/agent/traces/{run_id}', 'One trace with all steps'],
  ['GET', '/agent/analytics', 'Agent runs, success rate, tool usage'],
  ['GET', '/analytics/summary', 'Totals, percentiles, per-model breakdown, deltas'],
  ['GET', '/analytics/timeseries', 'Zero-filled time buckets'],
  ['GET', '/analytics/logs', 'Paginated, filterable call log'],
  ['GET', '/analytics/logs.csv', 'The filtered call log as CSV'],
  ['GET', '/analytics/filters', 'Models and providers seen in a window'],
  ['GET', '/evals/suites', 'List suites'],
  ['POST', '/evals/suites', 'Create a suite from JSON'],
  ['POST', '/evals/suites/import', 'Import YAML or JSON (same name adds a version)'],
  ['GET', '/evals/suites/{id}', 'A suite version with its definition'],
  ['PUT', '/evals/suites/{id}', 'Save a new version'],
  ['DELETE', '/evals/suites/{id}', 'Delete a suite, its runs and results'],
  ['GET', '/evals/suites/{id}/export', 'Export as YAML or JSON'],
  ['POST', '/evals/suites/{id}/preview', 'The exact messages a case would send'],
  ['PUT', '/evals/suites/{id}/baseline', 'Set or clear the baseline run'],
  ['POST', '/evals/runs', 'Start one run per variant'],
  ['GET', '/evals/runs', 'List runs (optionally for one suite)'],
  ['GET', '/evals/runs/{id}', 'Run status and totals'],
  ['DELETE', '/evals/runs/{id}', 'Delete a finished run'],
  ['GET', '/evals/runs/{id}/results', 'Per-case results (filter: passed, failed, error)'],
  ['POST', '/evals/runs/{id}/cancel', 'Cancel a run'],
  ['POST', '/evals/runs/{id}/resume', 'Resume a cancelled, interrupted or failed run'],
  ['GET', '/evals/compare', 'Compare a candidate run with a baseline'],
];

const ENV_GROUPS: { title: string; vars: [string, string, string][] }[] = [
  {
    title: 'Storage and secrets',
    vars: [
      ['DATABASE_URL', 'sqlite+aiosqlite:///./data/llmwatch.db', 'SQLite or postgresql+asyncpg://… (Docker uses /data)'],
      ['AUTO_MIGRATE', 'true', 'Run database migrations on startup'],
      ['SECRET_KEY', '(generated)', 'At least 32 characters. Unset: generated once and saved to SECRET_KEY_FILE'],
      ['SECRET_KEY_FILE', './data/secret_key', 'Where the generated key is kept (mode 0600)'],
      ['JWT_EXPIRE_HOURS', '24', 'Session token lifetime'],
    ],
  },
  {
    title: 'Providers seeded from the environment',
    vars: [
      ['OPENAI_API_KEY', '', 'Adds an OpenAI provider'],
      ['GOOGLE_API_KEY', '', 'Adds Gemini (OpenAI-compatible endpoint, GEMINI_BASE_URL)'],
      ['OPENROUTER_API_KEY', '', 'Adds OpenRouter'],
      ['GROQ_API_KEY', '', 'Adds Groq'],
      ['TOGETHER_API_KEY', '', 'Adds Together'],
      ['OLLAMA_BASE_URL', '', 'Adds Ollama, e.g. http://localhost:11434/v1'],
      ['VLLM_BASE_URL / VLLM_API_KEY', '', 'Adds a vLLM server'],
      ['QWEN_BASE_URL / QWEN_API_KEY', '', 'Legacy: a vLLM server for the "qwen" alias'],
      ['PROVIDER_ALLOW_PRIVATE_URLS', 'true', 'Allow provider base URLs on private networks (needed for local models)'],
    ],
  },
  {
    title: 'Access',
    vars: [
      ['ALLOW_SIGNUP', 'true', 'When false, only the first account can register (bootstrap, then closed)'],
      ['DEMO_MODE', 'false', 'Seed a demo user (refused when APP_ENV=production)'],
      ['DEMO_EMAIL / DEMO_PASSWORD', 'demo@llmwatch.dev / llmwatch-demo', 'Demo credentials'],
      ['CORS_ORIGINS', '', 'Comma-separated origins, only needed when the UI is on another origin'],
      ['APP_ENV', 'development', 'development or production'],
    ],
  },
  {
    title: 'Security',
    vars: [
      ['ENABLE_CODE_EXECUTION', 'false', 'Register the agent\'s python tool (resource-limited, not a sandbox)'],
      ['FETCH_ALLOWED_HOSTS', '', 'Hosts fetch_url may reach even though they resolve to private addresses (e.g. an intranet wiki)'],
      ['TRUSTED_PROXIES', '', 'CIDRs whose X-Forwarded-For is trusted (compose sets the Docker networks)'],
      ['RATE_LIMIT_ENABLED', 'true', 'Per-user/key/IP rate limits'],
      ['RATE_LIMIT_CHAT / RATE_LIMIT_AGENT', '60/minute / 10/minute', 'Limits for chat and agent runs'],
      ['RATE_LIMIT_PER_IP', '300/minute', 'Per client IP on the chat and agent routes, across all users and keys'],
      ['RATE_LIMIT_STORAGE_URI', 'memory://', 'Use redis://… when running several workers'],
    ],
  },
  {
    title: 'Evals',
    vars: [
      ['EVAL_MAX_CONCURRENCY', '32', 'Upper bound for a run\'s concurrency'],
      ['EVAL_PROVIDER_CONCURRENCY', '8', 'Parallel requests per provider across all runs'],
      ['EVAL_PROVIDER_RPM', '600', 'Requests per minute per provider'],
      ['EVAL_MAX_RETRIES', '5', 'Retries for rate limits, timeouts and 5xx'],
      ['EVAL_RETRY_BASE_S / EVAL_RETRY_MAX_S', '1.0 / 30.0', 'Backoff with jitter; Retry-After is honored'],
    ],
  },
  {
    title: 'Optional integrations',
    vars: [['MLFLOW_TRACKING_URI', '', 'Also log calls to MLflow (needs the mlflow extra)']],
  },
];

const EVALUATORS: [string, string][] = [
  ['exact_match', 'Output equals value (or the case\'s expected); options normalise case, whitespace and punctuation'],
  ['contains', 'Output contains value (a string or a list; mode: all or any; case_sensitive)'],
  ['not_contains', 'Output contains none of value'],
  ['regex', 'Output matches the pattern in value (flags: i, m, s)'],
  ['json_valid', 'Output is JSON (```json fences allowed)'],
  ['json_schema', 'Output is JSON that validates against the schema in value'],
  ['similarity', 'Embedding cosine similarity to value or expected is at least threshold'],
  ['llm_judge', 'A judge model scores the output against the rubric in value (JSON score and reasoning, temperature 0)'],
  ['latency_under', 'Latency is at most value milliseconds'],
  ['cost_under', 'Cost is at most value USD (fails when the model has no price)'],
];

/* ── Code block with copy button ───────────────────────────── */

function CodeBlock({
  children,
  language = 'bash',
  title,
}: {
  children: string;
  language?: string;
  title?: string;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    void navigator.clipboard.writeText(children.trim());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="rounded-xl border border-card-border overflow-hidden my-4">
      {title && (
        <div className="flex items-center justify-between px-4 py-2 border-b border-card-border bg-white/[0.02]">
          <span className="text-xs text-muted-foreground font-mono">{title}</span>
          <span className="text-[10px] text-muted-foreground/60 uppercase tracking-wider">{language}</span>
        </div>
      )}
      <div className="relative group">
        <pre className="p-4 overflow-x-auto text-sm leading-relaxed font-mono text-muted-foreground bg-black/20">
          <code>{children.trim()}</code>
        </pre>
        <button
          onClick={handleCopy}
          className="absolute top-3 right-3 p-1.5 rounded-md bg-white/[0.06] border border-card-border opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-foreground"
          title="Copy to clipboard"
          aria-label="Copy to clipboard"
        >
          {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />}
        </button>
      </div>
    </div>
  );
}

/* ── Endpoint badge ────────────────────────────────────────── */

function MethodBadge({ method }: { method: string }) {
  const colors: Record<string, string> = {
    GET: 'bg-success/15 text-success border-success/20',
    POST: 'bg-primary/15 text-primary border-primary/20',
    PUT: 'bg-warning/15 text-warning border-warning/20',
    PATCH: 'bg-warning/15 text-warning border-warning/20',
    DELETE: 'bg-error/15 text-error border-error/20',
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-mono font-semibold border ${colors[method] ?? 'bg-white/10 text-foreground border-card-border'}`}>
      {method}
    </span>
  );
}

/* ── Param table ───────────────────────────────────────────── */

function ParamTable({
  params,
}: {
  params: { name: string; type: string; required: boolean; description: string }[];
}) {
  return (
    <div className="rounded-xl border border-card-border overflow-hidden my-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-card-border bg-white/[0.02]">
            <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Parameter</th>
            <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Type</th>
            <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Required</th>
            <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Description</th>
          </tr>
        </thead>
        <tbody>
          {params.map((p) => (
            <tr key={p.name} className="border-b border-card-border last:border-0">
              <td className="px-4 py-2.5 font-mono text-foreground">{p.name}</td>
              <td className="px-4 py-2.5 font-mono text-primary/80">{p.type}</td>
              <td className="px-4 py-2.5">
                {p.required ? (
                  <span className="text-error text-xs font-medium">Required</span>
                ) : (
                  <span className="text-muted-foreground text-xs">Optional</span>
                )}
              </td>
              <td className="px-4 py-2.5 text-muted-foreground">{p.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Section heading with anchor ───────────────────────────── */

function SectionHeading({
  id,
  level = 2,
  children,
}: {
  id: string;
  level?: 2 | 3;
  children: React.ReactNode;
}) {
  const Tag = level === 2 ? 'h2' : 'h3';
  const sizeClass =
    level === 2 ? 'text-2xl font-bold mt-16 mb-6' : 'text-xl font-semibold mt-10 mb-4';

  return (
    <Tag id={id} className={`${sizeClass} tracking-tight scroll-mt-24 group flex items-center gap-2`}>
      {children}
      <a
        href={`#${id}`}
        className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-primary"
      >
        <Hash size={level === 2 ? 20 : 16} />
      </a>
    </Tag>
  );
}

/* ── Small content helpers ─────────────────────────────────── */

const P: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p className="text-muted-foreground leading-relaxed mb-4">{children}</p>
);

const C: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <code className="px-1.5 py-0.5 rounded bg-white/[0.06] font-mono text-[0.85em] text-foreground">{children}</code>
);

const Endpoint: React.FC<{ method: string; path: string }> = ({ method, path }) => (
  <div className="flex items-center gap-3 my-4">
    <MethodBadge method={method} />
    <code className="font-mono text-sm">{path}</code>
  </div>
);

const Callout: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="rounded-xl border border-warning/30 bg-warning/[0.06] p-4 my-4 text-sm text-muted-foreground leading-relaxed">
    {children}
  </div>
);

/* ── Main component ────────────────────────────────────────── */

const Docs: React.FC = () => {
  const [activeSection, setActiveSection] = useState('quickstart');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Highlight the section currently in view.
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.find((e) => e.isIntersecting);
        if (visible) setActiveSection(visible.target.id);
      },
      { rootMargin: '-80px 0px -60% 0px', threshold: 0.1 },
    );
    for (const id of navItems.flatMap((item) => item.children.map((c) => c.id))) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  const q = searchQuery.toLowerCase();
  const filteredNav = q
    ? navItems
        .map((item) => ({
          ...item,
          children: item.label.toLowerCase().includes(q) ? item.children : item.children.filter((c) => c.label.toLowerCase().includes(q)),
        }))
        .filter((item) => item.children.length > 0)
    : navItems;

  return (
    <div className="min-h-screen bg-background text-foreground font-sans">
      {/* ── Top navbar ──────────────────────────────────────── */}
      <nav className="fixed top-0 inset-x-0 z-50 backdrop-blur-xl bg-background/70 border-b border-card-border">
        <div className="max-w-[90rem] mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link to="/" className="flex items-center gap-2.5 group">
              <div className="w-8 h-8 bg-primary/20 text-primary rounded-lg flex items-center justify-center group-hover:scale-110 transition-transform">
                <Zap size={16} />
              </div>
              <span className="text-base font-bold tracking-tight">
                LLM<span className="text-gradient">Watch</span>
              </span>
            </Link>
            <ChevronRight size={14} className="text-muted-foreground/40" />
            <span className="text-sm text-muted-foreground">Docs</span>
          </div>

          <div className="flex items-center gap-3">
            <Link to="/" className="hidden sm:inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
              <ArrowLeft size={14} />
              Home
            </Link>
            <Link
              to="/login"
              className="text-sm font-medium bg-gradient-to-r from-primary to-primary-hover text-white px-4 py-1.5 rounded-lg shadow-[0_0_15px_rgba(59,130,246,0.2)] hover:shadow-[0_0_25px_rgba(59,130,246,0.35)] transition-all duration-300"
            >
              Sign in
            </Link>
            <button
              onClick={() => setMobileNavOpen(!mobileNavOpen)}
              className="lg:hidden p-1.5 text-muted-foreground hover:text-foreground"
              aria-label={mobileNavOpen ? 'Close navigation' : 'Open navigation'}
            >
              {mobileNavOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
      </nav>

      <div className="flex max-w-[90rem] mx-auto pt-14">
        {/* ── Sidebar ─────────────────────────────────────── */}
        <aside
          className={`fixed lg:sticky top-14 left-0 z-40 h-[calc(100vh-3.5rem)] w-72 border-r border-card-border bg-background lg:bg-transparent overflow-y-auto shrink-0 transition-transform duration-200 ${
            mobileNavOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
          }`}
        >
          <div className="p-4">
            <div className="relative mb-4">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/50" />
              <input
                type="text"
                placeholder="Search docs..."
                aria-label="Search docs"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 rounded-lg bg-white/[0.04] border border-card-border text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary/40 transition-colors"
              />
            </div>
            <nav className="space-y-1">
              {filteredNav.map((item) => (
                <div key={item.id}>
                  <div className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-muted-foreground">
                    {item.icon}
                    {item.label}
                  </div>
                  <div className="ml-4 border-l border-card-border space-y-0.5">
                    {item.children.map((child) => (
                      <a
                        key={child.id}
                        href={`#${child.id}`}
                        onClick={() => setMobileNavOpen(false)}
                        className={`block pl-4 pr-3 py-1.5 text-sm transition-colors rounded-r-md ${
                          activeSection === child.id
                            ? 'text-primary border-l-2 border-primary -ml-px bg-primary/[0.05]'
                            : 'text-muted-foreground hover:text-foreground'
                        }`}
                      >
                        {child.label}
                      </a>
                    ))}
                  </div>
                </div>
              ))}
            </nav>
          </div>
        </aside>

        {mobileNavOpen && <div className="fixed inset-0 bg-black/50 z-30 lg:hidden" onClick={() => setMobileNavOpen(false)} />}

        {/* ── Content ─────────────────────────────────────── */}
        <main className="flex-1 min-w-0 px-4 sm:px-6 md:px-12 py-10 max-w-4xl">
          <div className="mb-8">
            <span className="text-sm text-primary font-medium tracking-wide uppercase">Documentation</span>
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mt-2 mb-4">LLMWatch</h1>
            <p className="text-lg text-muted-foreground leading-relaxed">
              A self-hosted platform for LLM observability and evals: log every call with tokens, latency and cost,
              trace agent runs, and compare models and prompts with statistics that say when a difference is real.
            </p>
          </div>

          {/* ── Getting started ─────────────────────────── */}
          <SectionHeading id="quickstart">Quickstart</SectionHeading>
          <P>With Docker, no configuration is needed. The API and UI run behind one port with a SQLite database on a named volume.</P>
          <CodeBlock title="Terminal">
{`git clone https://github.com/omer-ulucan/llmwatch.git
cd llmwatch
docker compose up -d
# open http://localhost:3000 and create an account`}
          </CodeBlock>
          <P>
            On first boot the backend generates a secret key and stores it in the volume. Then open <b>Models</b>, add a provider (or set{' '}
            <C>OPENAI_API_KEY</C>, <C>OLLAMA_BASE_URL</C> and friends in a <C>.env</C> file next to <C>docker-compose.yml</C>), and discover its
            models. After you have created your account you can set <C>ALLOW_SIGNUP=false</C>.
          </P>

          <SectionHeading id="local-dev" level={3}>
            Local development
          </SectionHeading>
          <CodeBlock title="Backend (Python 3.11+)">
{`cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn llmwatch.main:app --reload      # http://localhost:8000, OpenAPI docs at /docs`}
          </CodeBlock>
          <CodeBlock title="Frontend (Node 20+)">
{`cd frontend
npm install
npm run dev                             # http://localhost:3000, proxies /api to :8000`}
          </CodeBlock>

          <SectionHeading id="demo-mode" level={3}>
            Demo mode
          </SectionHeading>
          <P>
            <C>DEMO_MODE=true</C> seeds a real user with <C>DEMO_EMAIL</C> / <C>DEMO_PASSWORD</C> and the example eval suite. It is for local
            exploration only: the server refuses to start with demo mode on when <C>APP_ENV=production</C>.
          </P>

          {/* ── Providers ───────────────────────────────── */}
          <SectionHeading id="providers-presets">Providers</SectionHeading>
          <P>
            A provider is any OpenAI-compatible endpoint. Presets fill in the base URL for OpenAI, Gemini, OpenRouter, Groq, Together, Ollama,
            vLLM and LM Studio; <b>Custom</b> takes any URL. Keys are encrypted at rest with a key derived from <C>SECRET_KEY</C> and the API
            only ever returns them masked. <b>Test</b> checks the connection; <b>Discover</b> imports the models the provider lists.
          </P>

          <SectionHeading id="providers-ollama" level={3}>
            Ollama and local models
          </SectionHeading>
          <P>
            Set <C>OLLAMA_BASE_URL=http://localhost:11434/v1</C> (or add an Ollama provider in the UI) and discover models. With Docker
            Compose, use <C>http://host.docker.internal:11434/v1</C> and start Ollama with <C>OLLAMA_HOST=0.0.0.0</C>, since by default it
            only listens on loopback, which containers cannot reach. Reasoning models are told not to think unless thinking is turned on, so
            short answers are not lost to hidden reasoning.
          </P>

          <SectionHeading id="models-refs" level={3}>
            Model references
          </SectionHeading>
          <P>Anywhere the API takes a model (chat, agent, eval variants, the CLI) you can pass:</P>
          <ul className="list-disc pl-6 mb-4 space-y-1 text-muted-foreground">
            <li>
              the model&apos;s id from <C>GET /models</C>,
            </li>
            <li>
              <C>Provider/model-id</C>, for example <C>Ollama/qwen3:8b</C> or <C>OpenAI/gpt-4o-mini</C>,
            </li>
            <li>
              <C>default</C>, the workspace&apos;s default model,
            </li>
            <li>
              the legacy aliases <C>qwen</C> and <C>gemini</C>, when those providers are configured.
            </li>
          </ul>
          <P>
            <C>GET /models/resolve?ref=…</C> shows what a reference points to.
          </P>

          <SectionHeading id="models-pricing" level={3}>
            Pricing and cost
          </SectionHeading>
          <P>
            Cost is computed from the token usage the provider reports and the per-million-token prices you set on each model. LLMWatch ships
            no price list, so a model without prices is shown as <i>unpriced</i> rather than $0. Eval runs store a snapshot of the prices
            they ran with.
          </P>

          {/* ── Auth ────────────────────────────────────── */}
          <SectionHeading id="auth-session">Accounts and sessions</SectionHeading>
          <P>
            Registering creates a workspace and makes you its owner. Every query is scoped to the caller&apos;s workspace. Log in to get a
            JWT and send it as a bearer token:
          </P>
          <CodeBlock title="cURL">
{`TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"email": "you@example.com", "password": "…"}' | jq -r .access_token)

curl http://localhost:8000/auth/me -H "Authorization: Bearer $TOKEN"`}
          </CodeBlock>

          <SectionHeading id="auth-api-keys" level={3}>
            API keys
          </SectionHeading>
          <P>
            For scripts and CI, create a key in <b>Settings</b> (it is shown once) and send it as <C>X-API-Key</C>. Keys can call everything
            except key management itself, which needs a signed-in session.
          </P>
          <CodeBlock title="cURL">
{`curl http://localhost:8000/analytics/summary?hours=24 -H "X-API-Key: lw_…"`}
          </CodeBlock>

          {/* ── Chat ────────────────────────────────────── */}
          <SectionHeading id="chat-completions">Chat completions</SectionHeading>
          <Endpoint method="POST" path="/chat/completions" />
          <ParamTable
            params={[
              { name: 'model', type: 'string', required: true, description: 'A model reference' },
              { name: 'prompt', type: 'string', required: false, description: 'A user message (prompt or messages is required)' },
              { name: 'messages', type: '{role, content}[]', required: false, description: 'Conversation history; prompt is appended last' },
              { name: 'system_prompt', type: 'string', required: false, description: 'System message' },
              { name: 'temperature', type: 'number', required: false, description: '0 to 2' },
              { name: 'max_tokens', type: 'integer', required: false, description: 'Output token limit' },
              { name: 'top_p', type: 'number', required: false, description: '0 to 1' },
              { name: 'thinking_mode', type: 'boolean', required: false, description: 'Let reasoning models think (default false)' },
            ]}
          />
          <P>
            The response has the text, any reasoning, token counts, latency, cost and whether the model was priced. Every call is logged,
            failures included.
          </P>

          <SectionHeading id="chat-stream" level={3}>
            Streaming
          </SectionHeading>
          <Endpoint method="POST" path="/chat/stream" />
          <P>
            Same body, answered as Server-Sent Events with one JSON object per <C>data:</C> line. Closing the connection stops the upstream
            request and the partial call is still logged.
          </P>
          <CodeBlock language="text" title="Events">
{`{"type": "start", "model_used", "model_id"}
{"type": "reasoning", "text"}         reasoning text, when the provider sends it
{"type": "delta", "text"}             answer text
{"type": "usage", "input_tokens", "output_tokens", "reasoning_tokens"}
{"type": "error", "error_type", "message"}
{"type": "done", "latency_ms", "cost_usd", "priced", "finish_reason"}`}
          </CodeBlock>

          {/* ── Agent ───────────────────────────────────── */}
          <SectionHeading id="agent-run">Run the agent</SectionHeading>
          <Endpoint method="POST" path="/agent/run" />
          <P>
            A native tool-calling loop: the model calls tools, sees their results, and repeats until it answers or reaches{' '}
            <C>max_iterations</C>. Use a model that supports tool calling.
          </P>
          <ParamTable
            params={[
              { name: 'prompt', type: 'string', required: true, description: 'The task' },
              { name: 'model', type: 'string', required: true, description: 'A model reference' },
              { name: 'tools', type: 'string[]', required: false, description: 'Defaults to every tool the server allows' },
              { name: 'max_iterations', type: 'integer', required: false, description: 'Model calls before stopping, 1 to 20 (default 10)' },
            ]}
          />
          <CodeBlock title="cURL">
{`curl -N -X POST http://localhost:8000/agent/run \\
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\
  -d '{"prompt": "What did I spend on LLM calls today, by model?", "model": "default", "tools": ["query_usage"]}'`}
          </CodeBlock>

          <SectionHeading id="agent-tools" level={3}>
            Tools
          </SectionHeading>
          <ul className="list-disc pl-6 mb-4 space-y-2 text-muted-foreground">
            <li>
              <C>web_search</C>: web search through DuckDuckGo.
            </li>
            <li>
              <C>fetch_url</C>: fetches a page and extracts its text. Private, loopback, link-local and cloud metadata addresses are refused,
              every redirect is re-checked, and the connection is pinned to the vetted IP. Hosts in <C>FETCH_ALLOWED_HOSTS</C> are exempt from the private-address check.
            </li>
            <li>
              <C>query_usage</C>: answers questions about your own usage from the database (scoped to your workspace).
            </li>
            <li>
              <C>python</C>: only registered when <C>ENABLE_CODE_EXECUTION=true</C>.
            </li>
          </ul>
          <Callout>
            The python tool runs code in an isolated interpreter with an empty environment, a temporary directory, CPU, memory and file limits
            and a timeout. That reduces the damage a bad snippet can do, but it is <b>not a sandbox</b>: only enable it on a machine where
            running untrusted code is acceptable.
          </Callout>

          <SectionHeading id="agent-events" level={3}>
            Events and traces
          </SectionHeading>
          <P>
            The run streams <C>run_start</C>, <C>thinking</C> (a model call), <C>tool_call</C>, <C>tool_result</C>, <C>final_answer</C>,{' '}
            <C>error</C> and <C>run_end</C> events, each with latency, tokens and cost where they apply. The whole run is saved as a trace
            (also when it fails or is cancelled) and can be read from <C>GET /agent/traces/{'{run_id}'}</C>. Cancel with{' '}
            <C>POST /agent/runs/{'{run_id}'}/cancel</C> or by closing the stream.
          </P>

          {/* ── Evals ───────────────────────────────────── */}
          <SectionHeading id="evals-suites">Suite format</SectionHeading>
          <P>
            A suite is a prompt template plus cases. <C>{'{{ variable }}'}</C> placeholders are filled from each case&apos;s <C>vars</C>; a
            missing variable is an error, and templates cannot run code. Assertions on the suite apply to every case. Editing a suite saves a
            new immutable version, and runs keep pointing at the version they ran.
          </P>
          <CodeBlock language="yaml" title="capitals.yaml">
{`name: capitals
description: One-word answers
system_prompt: You are a concise assistant.
prompt: |
  Answer with one word: what is the capital of {{ country }}?
assert:                       # applies to every case
  - type: not_contains
    value: "I'm not sure"
cases:
  - id: france
    vars: {country: France}
    expected: Paris
    assert:
      - {type: contains, value: Paris, case_sensitive: false}
  - id: japan
    vars: {country: Japan}
    tags: [asia]
    assert:
      - {type: contains, value: Tokyo, case_sensitive: false}
      - {type: latency_under, value: 5000, weight: 0.5}`}
          </CodeBlock>
          <P>
            A case&apos;s score is the weighted mean of its assertion scores, and it passes only when every assertion passes. A complete
            example lives in <C>examples/support-triage.yaml</C>.
          </P>

          <SectionHeading id="evals-evaluators" level={3}>
            Evaluators
          </SectionHeading>
          <div className="rounded-xl border border-card-border overflow-x-auto my-4">
            <table className="w-full text-sm">
              <tbody>
                {EVALUATORS.map(([type, desc]) => (
                  <tr key={type} className="border-b border-card-border last:border-0 align-top">
                    <td className="px-4 py-2.5 font-mono whitespace-nowrap">{type}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <P>
            Each evaluator returns a score from 0 to 1, pass or fail, and a reason. <C>llm_judge</C> warns when the judge and the candidate
            come from the same model family, since judges tend to favour their own family.
          </P>

          <SectionHeading id="evals-runs" level={3}>
            Runs
          </SectionHeading>
          <P>
            <C>POST /evals/runs</C> starts one run per variant (a model plus temperature, max tokens and thinking) with optional repeats,
            concurrency and judge model. Runs execute in the background with bounded concurrency, a per-provider rate limit, and retries with
            jittered backoff that honor <C>Retry-After</C>. Responses are cached by model, parameters, messages and repeat number, so
            re-running an unchanged variant costs nothing. A run that was cancelled or cut short by a restart can be resumed.
          </P>

          <SectionHeading id="evals-compare" level={3}>
            Comparisons
          </SectionHeading>
          <P>
            <C>GET /evals/compare?baseline=…&amp;candidate=…</C> pairs results by case and repeat and reports:
          </P>
          <ul className="list-disc pl-6 mb-4 space-y-1 text-muted-foreground">
            <li>the mean score delta with a 95% paired-bootstrap confidence interval (10,000 resamples, seeded),</li>
            <li>pass-rate change with McNemar&apos;s test (exact below 25 discordant pairs, χ² with continuity correction above),</li>
            <li>cost per case and latency deltas,</li>
            <li>which cases regressed, were fixed or stayed the same.</li>
          </ul>
          <P>
            The verdict is &quot;no significant difference&quot; unless a test says otherwise. With fewer than 10 paired cases the interval
            is not used for significance, and the response carries warnings for that, for different suite versions and for unpriced models.
            Mark a run as the suite&apos;s baseline to compare against it by default.
          </P>

          <SectionHeading id="evals-cli" level={3}>
            CLI and CI
          </SectionHeading>
          <P>
            The <C>llmwatch</C> command is installed with the backend. It works against the local database or, with <C>--server</C>, a
            running instance.
          </P>
          <CodeBlock title="Terminal">
{`llmwatch eval run examples/support-triage.yaml --model Ollama/qwen3:8b --set-baseline

llmwatch eval run examples/support-triage.yaml --model OpenAI/gpt-4o-mini \\
  --server https://llmwatch.example.com --api-key "$LLMWATCH_API_KEY" \\
  --baseline <run-id> --fail-on-regression --json

llmwatch eval compare <baseline-run-id> <candidate-run-id>`}
          </CodeBlock>
          <P>
            <C>--baseline</C> takes a run id or <C>suite</C> for the suite&apos;s baseline. Other options: <C>--param temperature=0</C>, <C>--repeats</C>, <C>--concurrency</C>, <C>--judge-model</C>,{' '}
            <C>--embedding-model</C>, <C>--thinking</C>, <C>--no-cache</C>. Exit codes: <b>0</b> success, <b>1</b> significant regression
            (with <C>--fail-on-regression</C>), <b>2</b> usage or configuration error.
          </P>

          {/* ── Analytics ───────────────────────────────── */}
          <SectionHeading id="analytics-endpoints">Analytics</SectionHeading>
          <P>
            All analytics endpoints take a window as <C>?hours=24</C> or <C>?from=…&amp;to=…</C> (ISO 8601) and filters such as{' '}
            <C>model</C>, <C>provider</C>, <C>status</C> and <C>source</C> (chat, agent, eval).
          </P>
          <ul className="list-disc pl-6 mb-4 space-y-1 text-muted-foreground">
            <li>
              <C>/analytics/summary</C>: requests, errors, p50/p95 latency, tokens, cost, per-model breakdown, and changes against the
              previous window of the same length.
            </li>
            <li>
              <C>/analytics/timeseries</C>: zero-filled buckets sized to the window.
            </li>
            <li>
              <C>/analytics/logs</C>: the call log, newest first, with <C>q</C> to search prompts, responses and errors.
            </li>
            <li>
              <C>/analytics/logs.csv</C>: the same filtered log as CSV.
            </li>
          </ul>

          {/* ── Reference ───────────────────────────────── */}
          <SectionHeading id="api-endpoints">All endpoints</SectionHeading>
          <P>
            Paths are relative to the API root: <C>http://localhost:8000</C> in development, <C>/api</C> behind the bundled nginx. Everything
            except <C>/health</C>, register and login needs a bearer token or API key.
          </P>
          <div className="rounded-xl border border-card-border overflow-x-auto my-4">
            <table className="w-full text-sm">
              <tbody>
                {ENDPOINTS.map(([method, path, desc]) => (
                  <tr key={method + path} className="border-b border-card-border last:border-0">
                    <td className="px-4 py-2 w-20">
                      <MethodBadge method={method} />
                    </td>
                    <td className="px-4 py-2 font-mono whitespace-nowrap">{path}</td>
                    <td className="px-4 py-2 text-muted-foreground">{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <SectionHeading id="config-env" level={3}>
            Configuration
          </SectionHeading>
          <P>
            All settings are environment variables (or a <C>.env</C> file). None is required.
          </P>
          {ENV_GROUPS.map((group) => (
            <div key={group.title} className="mb-6">
              <h4 className="font-semibold mb-2 flex items-center gap-2">
                <Settings size={14} className="text-muted-foreground" /> {group.title}
              </h4>
              <div className="rounded-xl border border-card-border overflow-x-auto">
                <table className="w-full text-sm">
                  <tbody>
                    {group.vars.map(([name, def, desc]) => (
                      <tr key={name} className="border-b border-card-border last:border-0 align-top">
                        <td className="px-4 py-2 font-mono whitespace-nowrap">{name}</td>
                        <td className="px-4 py-2 font-mono text-xs text-muted-foreground whitespace-nowrap">{def || '—'}</td>
                        <td className="px-4 py-2 text-muted-foreground">{desc}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}

          <SectionHeading id="errors" level={3}>
            Errors
          </SectionHeading>
          <P>
            Errors are JSON with an <C>error</C> message. Validation problems return 422 with details, missing or invalid credentials 401,
            insufficient role 403, unknown resources 404, rate limits 429, and provider failures 502 with the provider&apos;s message.
          </P>
          <div className="h-24" />
        </main>
      </div>
    </div>
  );
};

export default Docs;
