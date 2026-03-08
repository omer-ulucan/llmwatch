/**
 * Component: Docs
 * Purpose: Full platform documentation — public page accessible without authentication.
 * WHY: Prospective and current users need a single reference for the API, SDKs,
 * agent system, tracing, analytics, auth, and configuration.
 */
import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router';
import {
  Zap,
  ChevronRight,
  ArrowLeft,
  Search,
  Book,
  Key,
  Terminal,
  Bot,
  Activity,
  BarChart3,
  Settings,
  Copy,
  Check,
  Hash,
  Menu,
  X,
} from 'lucide-react';

/* ── Types ─────────────────────────────────────────────────── */

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  children?: { id: string; label: string }[];
}

/* ── Sidebar navigation structure ──────────────────────────── */

const navItems: NavItem[] = [
  {
    id: 'getting-started',
    label: 'Getting Started',
    icon: <Book size={16} />,
    children: [
      { id: 'quickstart', label: 'Quickstart' },
      { id: 'installation', label: 'Installation' },
      { id: 'demo-mode', label: 'Demo Mode' },
    ],
  },
  {
    id: 'authentication',
    label: 'Authentication',
    icon: <Key size={16} />,
    children: [
      { id: 'auth-overview', label: 'Overview' },
      { id: 'auth-register', label: 'Register' },
      { id: 'auth-login', label: 'Login' },
      { id: 'auth-tokens', label: 'Using Tokens' },
    ],
  },
  {
    id: 'api-reference',
    label: 'API Reference',
    icon: <Terminal size={16} />,
    children: [
      { id: 'api-health', label: 'Health Check' },
      { id: 'api-chat', label: 'Chat Completions' },
      { id: 'api-analytics-summary', label: 'Analytics Summary' },
      { id: 'api-analytics-logs', label: 'Analytics Logs' },
      { id: 'api-analytics-timeseries', label: 'Analytics Timeseries' },
    ],
  },
  {
    id: 'agent-system',
    label: 'Agent System',
    icon: <Bot size={16} />,
    children: [
      { id: 'agent-overview', label: 'Overview' },
      { id: 'agent-run', label: 'Run Agent' },
      { id: 'agent-tools', label: 'Available Tools' },
      { id: 'agent-sse', label: 'SSE Streaming' },
    ],
  },
  {
    id: 'tracing',
    label: 'Tracing',
    icon: <Activity size={16} />,
    children: [
      { id: 'tracing-overview', label: 'Overview' },
      { id: 'tracing-list', label: 'List Traces' },
      { id: 'tracing-detail', label: 'Trace Detail' },
      { id: 'tracing-events', label: 'Event Types' },
    ],
  },
  {
    id: 'analytics',
    label: 'Analytics',
    icon: <BarChart3 size={16} />,
    children: [
      { id: 'analytics-overview', label: 'Overview' },
      { id: 'analytics-agent', label: 'Agent Analytics' },
    ],
  },
  {
    id: 'configuration',
    label: 'Configuration',
    icon: <Settings size={16} />,
    children: [
      { id: 'config-env', label: 'Environment Variables' },
      { id: 'config-docker', label: 'Docker Compose' },
      { id: 'config-models', label: 'Model Configuration' },
    ],
  },
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
    navigator.clipboard.writeText(children.trim());
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

/* ── Main component ────────────────────────────────────────── */

const Docs: React.FC = () => {
  const [activeSection, setActiveSection] = useState('quickstart');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const contentRef = useRef<HTMLDivElement>(null);

  // Track active section on scroll
  useEffect(() => {
    const allIds = navItems.flatMap((item) =>
      item.children ? item.children.map((c) => c.id) : [item.id],
    );

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id);
            break;
          }
        }
      },
      { rootMargin: '-80px 0px -60% 0px', threshold: 0.1 },
    );

    for (const id of allIds) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }

    return () => observer.disconnect();
  }, []);

  // Filter nav items by search
  const filteredNav = searchQuery
    ? navItems
        .map((item) => ({
          ...item,
          children: item.children?.filter((c) =>
            c.label.toLowerCase().includes(searchQuery.toLowerCase()),
          ),
        }))
        .filter(
          (item) =>
            item.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
            (item.children && item.children.length > 0),
        )
    : navItems;

  return (
    <div className="min-h-screen bg-background text-foreground font-sans">
      {/* ── Top navbar ──────────────────────────────────────── */}
      <nav className="fixed top-0 inset-x-0 z-50 backdrop-blur-xl bg-background/70 border-b border-card-border">
        <div className="max-w-[90rem] mx-auto px-6 h-14 flex items-center justify-between">
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
            <span className="text-sm text-muted-foreground">Documentation</span>
          </div>

          <div className="flex items-center gap-3">
            <Link
              to="/"
              className="hidden sm:inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft size={14} />
              Home
            </Link>
            <Link
              to="/login"
              className="text-sm font-medium bg-gradient-to-r from-primary to-primary-hover text-white px-4 py-1.5 rounded-lg shadow-[0_0_15px_rgba(59,130,246,0.2)] hover:shadow-[0_0_25px_rgba(59,130,246,0.35)] transition-all duration-300"
            >
              Try Demo
            </Link>
            <button
              onClick={() => setMobileNavOpen(!mobileNavOpen)}
              className="lg:hidden p-1.5 text-muted-foreground hover:text-foreground"
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
            {/* Search */}
            <div className="relative mb-4">
              <Search
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/50"
              />
              <input
                type="text"
                placeholder="Search docs..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 rounded-lg bg-white/[0.04] border border-card-border text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary/40 transition-colors"
              />
            </div>

            {/* Nav tree */}
            <nav className="space-y-1">
              {filteredNav.map((item) => (
                <div key={item.id}>
                  <div className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-muted-foreground">
                    {item.icon}
                    {item.label}
                  </div>
                  {item.children && (
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
                  )}
                </div>
              ))}
            </nav>
          </div>
        </aside>

        {/* ── Mobile overlay ──────────────────────────────── */}
        {mobileNavOpen && (
          <div
            className="fixed inset-0 bg-black/50 z-30 lg:hidden"
            onClick={() => setMobileNavOpen(false)}
          />
        )}

        {/* ── Content ─────────────────────────────────────── */}
        <main ref={contentRef} className="flex-1 min-w-0 px-6 md:px-12 py-10 max-w-4xl">
          {/* ─────────────────────────────────────────────── */}
          {/* GETTING STARTED                                 */}
          {/* ─────────────────────────────────────────────── */}

          <div className="mb-8">
            <span className="text-sm text-primary font-medium tracking-wide uppercase">
              Getting Started
            </span>
            <h1 className="text-4xl font-bold tracking-tight mt-2 mb-4">
              LLMWatch Documentation
            </h1>
            <p className="text-lg text-muted-foreground leading-relaxed">
              Everything you need to integrate, monitor, and optimize your AI operations
              with LLMWatch.
            </p>
          </div>

          <SectionHeading id="quickstart" level={2}>
            Quickstart
          </SectionHeading>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Get up and running in under five minutes. LLMWatch provides a single API
            endpoint for all your LLM interactions, with automatic tracing, cost tracking,
            and performance monitoring.
          </p>

          <div className="glass-card rounded-2xl p-6 my-6">
            <h4 className="font-semibold mb-3">1. Send your first request</h4>
            <p className="text-sm text-muted-foreground mb-3">
              After logging in and obtaining a JWT token, make a chat completion request:
            </p>
            <CodeBlock language="bash" title="cURL">
{`curl -X POST http://localhost:8000/chat/completions \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "Explain quantum computing in simple terms",
    "model": "gemini"
  }'`}
            </CodeBlock>
          </div>

          <div className="glass-card rounded-2xl p-6 my-6">
            <h4 className="font-semibold mb-3">2. Check your analytics</h4>
            <p className="text-sm text-muted-foreground mb-3">
              View aggregated metrics for all your LLM calls:
            </p>
            <CodeBlock language="bash" title="cURL">
{`curl http://localhost:8000/analytics/summary \\
  -H "Authorization: Bearer YOUR_TOKEN"`}
            </CodeBlock>
          </div>

          <div className="glass-card rounded-2xl p-6 my-6">
            <h4 className="font-semibold mb-3">3. Run an agent</h4>
            <p className="text-sm text-muted-foreground mb-3">
              Execute an autonomous ReAct agent with built-in tools and real-time streaming:
            </p>
            <CodeBlock language="bash" title="cURL">
{`curl -N -X POST http://localhost:8000/agent/run \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "Search the web for the latest AI news and summarize it",
    "model": "gemini",
    "tools": ["web_search", "doc_analyze"]
  }'`}
            </CodeBlock>
          </div>

          {/* Installation */}
          <SectionHeading id="installation" level={2}>
            Installation
          </SectionHeading>

          <p className="text-muted-foreground leading-relaxed mb-4">
            LLMWatch runs as a Docker Compose stack with three services: the FastAPI backend,
            the React frontend, and MLFlow for experiment tracking.
          </p>

          <h4 className="font-semibold mb-2 mt-6">Prerequisites</h4>
          <ul className="list-disc list-inside text-muted-foreground space-y-1 mb-4">
            <li>Docker and Docker Compose v2+</li>
            <li>A Google Gemini API key (for Gemini model)</li>
            <li>A vLLM endpoint with Qwen (for Qwen model) — or use Gemini only</li>
            <li>AWS credentials for DynamoDB (or use Demo Mode without a database)</li>
          </ul>

          <h4 className="font-semibold mb-2 mt-6">1. Clone and configure</h4>
          <CodeBlock language="bash" title="Terminal">
{`git clone https://github.com/your-org/llmwatch.git
cd llmwatch

# Copy the example environment file
cp .env.example backend/.env

# Edit backend/.env with your credentials
# At minimum, set: JWT_SECRET_KEY, GOOGLE_API_KEY, CORS_ORIGINS`}
          </CodeBlock>

          <h4 className="font-semibold mb-2 mt-6">2. Start the stack</h4>
          <CodeBlock language="bash" title="Terminal">
{`docker compose up -d

# Services:
#   Frontend  → http://localhost:3000
#   Backend   → http://localhost:8000
#   MLFlow    → http://localhost:5000`}
          </CodeBlock>

          <h4 className="font-semibold mb-2 mt-6">3. Local development (without Docker)</h4>
          <CodeBlock language="bash" title="Terminal">
{`# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (in a separate terminal)
cd frontend
npm install
npm run dev   # → http://localhost:5173`}
          </CodeBlock>

          {/* Demo Mode */}
          <SectionHeading id="demo-mode" level={2}>
            Demo Mode
          </SectionHeading>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Demo mode allows you to explore the entire platform without configuring AWS
            DynamoDB. When enabled, the login endpoint accepts hardcoded credentials and
            returns a valid JWT token.
          </p>

          <div className="glass-card rounded-2xl p-6 my-6">
            <h4 className="font-semibold mb-3">Enable demo mode</h4>
            <p className="text-sm text-muted-foreground mb-3">
              Set the following in your <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">backend/.env</code> file:
            </p>
            <CodeBlock language="env" title=".env">
{`DEMO_MODE=true`}
            </CodeBlock>
          </div>

          <div className="glass-card rounded-2xl p-6 my-6">
            <h4 className="font-semibold mb-3">Demo credentials</h4>
            <ParamTable
              params={[
                { name: 'email', type: 'string', required: true, description: 'admin@company.com' },
                { name: 'password', type: 'string', required: true, description: 'admin123' },
              ]}
            />
            <p className="text-xs text-muted-foreground mt-2">
              The demo user is assigned <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">user_id: demo-user-001</code> and{' '}
              <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">company_id: demo-company-001</code>.
              All authenticated endpoints work normally with the returned token.
            </p>
          </div>

          {/* ─────────────────────────────────────────────── */}
          {/* AUTHENTICATION                                  */}
          {/* ─────────────────────────────────────────────── */}

          <SectionHeading id="auth-overview" level={2}>
            Authentication Overview
          </SectionHeading>

          <p className="text-muted-foreground leading-relaxed mb-4">
            LLMWatch uses stateless JWT (JSON Web Tokens) for authentication. Tokens are
            signed with HS256 and expire after 24 hours by default. All protected endpoints
            require a valid token in the <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">Authorization</code> header.
          </p>

          <div className="glass-card rounded-2xl p-6 my-6">
            <h4 className="font-semibold mb-3">Auth flow</h4>
            <div className="space-y-3 text-sm text-muted-foreground">
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-primary/15 text-primary flex items-center justify-center shrink-0 text-xs font-semibold">1</span>
                <span>Client calls <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">POST /auth/login</code> with email and password.</span>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-primary/15 text-primary flex items-center justify-center shrink-0 text-xs font-semibold">2</span>
                <span>Server validates credentials and returns a <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">TokenResponse</code> with the JWT.</span>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-primary/15 text-primary flex items-center justify-center shrink-0 text-xs font-semibold">3</span>
                <span>Client includes <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">Authorization: Bearer &lt;token&gt;</code> on all subsequent requests.</span>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-primary/15 text-primary flex items-center justify-center shrink-0 text-xs font-semibold">4</span>
                <span>Token is verified on each request. Expired or invalid tokens return <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">401 Unauthorized</code>.</span>
              </div>
            </div>
          </div>

          <div className="glass-card rounded-2xl p-6 my-6">
            <h4 className="font-semibold mb-3">JWT payload structure</h4>
            <CodeBlock language="json" title="Decoded JWT payload">
{`{
  "sub": "demo-user-001",
  "company_id": "demo-company-001",
  "exp": 1741478400
}`}
            </CodeBlock>
            <p className="text-xs text-muted-foreground mt-2">
              The <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">sub</code> field is the user ID. The <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">company_id</code> ensures
              multi-tenant data isolation — users can only access their own organization's data.
            </p>
          </div>

          {/* Register */}
          <SectionHeading id="auth-register" level={3}>
            Register
          </SectionHeading>

          <div className="flex items-center gap-3 mb-4">
            <MethodBadge method="POST" />
            <code className="text-sm font-mono text-foreground">/auth/register</code>
            <span className="text-xs text-muted-foreground ml-2">No auth required</span>
          </div>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Creates a new company and admin user account. Returns the assigned company ID.
          </p>

          <h4 className="font-semibold text-sm mb-2">Request body</h4>
          <ParamTable
            params={[
              { name: 'email', type: 'EmailStr', required: true, description: 'Valid email address' },
              { name: 'password', type: 'string', required: true, description: 'Minimum 8 characters' },
              { name: 'company_name', type: 'string', required: true, description: 'Organization name' },
            ]}
          />

          <CodeBlock language="bash" title="Example request">
{`curl -X POST http://localhost:8000/auth/register \\
  -H "Content-Type: application/json" \\
  -d '{
    "email": "user@example.com",
    "password": "securepass123",
    "company_name": "Acme Corp"
  }'`}
          </CodeBlock>

          <CodeBlock language="json" title="Response — 200 OK">
{`{
  "message": "User registered successfully",
  "company_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}`}
          </CodeBlock>

          {/* Login */}
          <SectionHeading id="auth-login" level={3}>
            Login
          </SectionHeading>

          <div className="flex items-center gap-3 mb-4">
            <MethodBadge method="POST" />
            <code className="text-sm font-mono text-foreground">/auth/login</code>
            <span className="text-xs text-muted-foreground ml-2">No auth required</span>
          </div>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Authenticates a user and returns a JWT token. In demo mode, accepts hardcoded
            credentials without requiring a database.
          </p>

          <h4 className="font-semibold text-sm mb-2">Request body</h4>
          <ParamTable
            params={[
              { name: 'email', type: 'EmailStr', required: true, description: 'Registered email address' },
              { name: 'password', type: 'string', required: true, description: 'Account password' },
            ]}
          />

          <CodeBlock language="bash" title="Example request">
{`curl -X POST http://localhost:8000/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{
    "email": "admin@company.com",
    "password": "admin123"
  }'`}
          </CodeBlock>

          <CodeBlock language="json" title="Response — 200 OK">
{`{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}`}
          </CodeBlock>

          {/* Using Tokens */}
          <SectionHeading id="auth-tokens" level={3}>
            Using Tokens
          </SectionHeading>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Include the JWT token in the <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">Authorization</code> header
            for all protected endpoints:
          </p>

          <CodeBlock language="bash" title="Authenticated request">
{`curl http://localhost:8000/analytics/summary \\
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."`}
          </CodeBlock>

          <div className="glass-card rounded-2xl p-6 my-6">
            <h4 className="font-semibold mb-3">Protected endpoints</h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
              {[
                'POST /chat/completions',
                'GET /analytics/summary',
                'GET /analytics/logs',
                'GET /analytics/timeseries',
                'POST /agent/run',
                'GET /agent/traces',
                'GET /agent/traces/:id',
                'GET /agent/analytics',
              ].map((ep) => (
                <div key={ep} className="flex items-center gap-2 text-muted-foreground">
                  <div className="w-1.5 h-1.5 rounded-full bg-error/60" />
                  <code className="font-mono text-xs">{ep}</code>
                </div>
              ))}
            </div>
          </div>

          <div className="glass-card rounded-2xl p-6 my-6 border-error/20">
            <h4 className="font-semibold mb-2 text-error">Error responses</h4>
            <p className="text-sm text-muted-foreground mb-3">
              Invalid or expired tokens return:
            </p>
            <CodeBlock language="json" title="401 Unauthorized">
{`{
  "error": "Token has expired",
  "code": "AUTHENTICATION_FAILED"
}`}
            </CodeBlock>
          </div>

          {/* ─────────────────────────────────────────────── */}
          {/* API REFERENCE                                   */}
          {/* ─────────────────────────────────────────────── */}

          <SectionHeading id="api-health" level={2}>
            Health Check
          </SectionHeading>

          <div className="flex items-center gap-3 mb-4">
            <MethodBadge method="GET" />
            <code className="text-sm font-mono text-foreground">/health</code>
            <span className="text-xs text-muted-foreground ml-2">No auth required</span>
            <span className="text-xs text-warning ml-1">Rate limited: 10/min</span>
          </div>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Returns application health status. Use this endpoint for load balancer health
            probes and uptime monitoring.
          </p>

          <CodeBlock language="json" title="Response — 200 OK">
{`{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": 1741392000.0,
  "uptime_seconds": 3600.5
}`}
          </CodeBlock>

          {/* Chat Completions */}
          <SectionHeading id="api-chat" level={2}>
            Chat Completions
          </SectionHeading>

          <div className="flex items-center gap-3 mb-4">
            <MethodBadge method="POST" />
            <code className="text-sm font-mono text-foreground">/chat/completions</code>
            <span className="text-xs text-error ml-2">Auth required</span>
          </div>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Send a prompt to the selected LLM model and receive a completion response with
            latency, token counts, and cost metrics. Logs are automatically saved to DynamoDB
            and MLFlow in the background.
          </p>

          <h4 className="font-semibold text-sm mb-2">Request body</h4>
          <ParamTable
            params={[
              { name: 'prompt', type: 'string', required: true, description: 'The user prompt. Maximum 10,000 characters.' },
              { name: 'model', type: '"qwen" | "gemini"', required: true, description: 'Target model. Must be exactly "qwen" or "gemini".' },
              { name: 'thinking_mode', type: 'boolean', required: false, description: 'Enable chain-of-thought reasoning. Default: false.' },
            ]}
          />

          <CodeBlock language="bash" title="Example request">
{`curl -X POST http://localhost:8000/chat/completions \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "What are the benefits of microservices?",
    "model": "gemini",
    "thinking_mode": true
  }'`}
          </CodeBlock>

          <h4 className="font-semibold text-sm mb-2 mt-6">Response fields</h4>
          <ParamTable
            params={[
              { name: 'response', type: 'string', required: true, description: 'The generated completion text.' },
              { name: 'thinking_content', type: 'string | null', required: false, description: 'Chain-of-thought reasoning (only when thinking_mode is true).' },
              { name: 'latency_ms', type: 'float', required: true, description: 'Response time in milliseconds.' },
              { name: 'input_tokens', type: 'integer', required: true, description: 'Number of prompt tokens consumed.' },
              { name: 'output_tokens', type: 'integer', required: true, description: 'Number of completion tokens generated.' },
              { name: 'cost_usd', type: 'float', required: true, description: 'Estimated cost in USD.' },
              { name: 'model_used', type: 'string', required: true, description: 'Which model was used for the completion.' },
              { name: 'thinking_mode', type: 'boolean', required: true, description: 'Whether thinking mode was active.' },
            ]}
          />

          <CodeBlock language="json" title="Response — 200 OK">
{`{
  "response": "Microservices offer several key benefits...",
  "thinking_content": "Let me think about this systematically...",
  "latency_ms": 1250.5,
  "input_tokens": 12,
  "output_tokens": 340,
  "cost_usd": 0.001024,
  "model_used": "gemini",
  "thinking_mode": true
}`}
          </CodeBlock>

          {/* Analytics Summary */}
          <SectionHeading id="api-analytics-summary" level={2}>
            Analytics Summary
          </SectionHeading>

          <div className="flex items-center gap-3 mb-4">
            <MethodBadge method="GET" />
            <code className="text-sm font-mono text-foreground">/analytics/summary</code>
            <span className="text-xs text-error ml-2">Auth required</span>
          </div>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Returns aggregated KPI metrics computed from your most recent 500 LLM call logs.
            Includes total cost, average latency, request count, error rate, and per-model breakdown.
          </p>

          <CodeBlock language="json" title="Response — 200 OK">
{`{
  "total_cost_usd": 12.456789,
  "avg_latency_ms": 245.67,
  "total_requests": 1250,
  "error_rate_pct": 0.24,
  "model_breakdown": {
    "qwen": { "requests": 800, "cost": 4.12 },
    "gemini": { "requests": 450, "cost": 8.34 }
  }
}`}
          </CodeBlock>

          {/* Analytics Logs */}
          <SectionHeading id="api-analytics-logs" level={2}>
            Analytics Logs
          </SectionHeading>

          <div className="flex items-center gap-3 mb-4">
            <MethodBadge method="GET" />
            <code className="text-sm font-mono text-foreground">/analytics/logs</code>
            <span className="text-xs text-error ml-2">Auth required</span>
          </div>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Returns raw invocation log entries. Supports filtering by model and pagination via limit.
          </p>

          <h4 className="font-semibold text-sm mb-2">Query parameters</h4>
          <ParamTable
            params={[
              { name: 'limit', type: 'integer', required: false, description: 'Max entries to return. Default: 50.' },
              { name: 'model', type: 'string', required: false, description: 'Filter by model name ("qwen", "gemini"). Default: "all".' },
            ]}
          />

          <CodeBlock language="bash" title="Example request">
{`curl "http://localhost:8000/analytics/logs?limit=10&model=gemini" \\
  -H "Authorization: Bearer YOUR_TOKEN"`}
          </CodeBlock>

          <CodeBlock language="json" title="Response — 200 OK (truncated)">
{`[
  {
    "log_id": "abc123",
    "timestamp": "2026-03-07T12:00:00Z",
    "prompt_preview": "What are the benefits...",
    "response_preview": "Microservices offer...",
    "model_name": "gemini",
    "latency_ms": 1250.5,
    "input_tokens": 12,
    "output_tokens": 340,
    "cost_usd": 0.001024,
    "thinking_mode": true,
    "success": true,
    "error_type": null
  }
]`}
          </CodeBlock>

          {/* Analytics Timeseries */}
          <SectionHeading id="api-analytics-timeseries" level={2}>
            Analytics Timeseries
          </SectionHeading>

          <div className="flex items-center gap-3 mb-4">
            <MethodBadge method="GET" />
            <code className="text-sm font-mono text-foreground">/analytics/timeseries</code>
            <span className="text-xs text-error ml-2">Auth required</span>
          </div>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Returns metric arrays optimized for charting (compatible with Recharts AreaChart).
            Each array index corresponds to the same log entry.
          </p>

          <h4 className="font-semibold text-sm mb-2">Query parameters</h4>
          <ParamTable
            params={[
              { name: 'hours', type: 'integer', required: false, description: 'Time window in hours. Default: 24.' },
            ]}
          />

          <CodeBlock language="json" title="Response — 200 OK">
{`{
  "timestamps": ["2026-03-07T11:00:00Z", "2026-03-07T11:05:00Z"],
  "costs": [0.0012, 0.0008],
  "latencies": [1250.5, 890.2],
  "request_counts": [1, 1]
}`}
          </CodeBlock>

          {/* ─────────────────────────────────────────────── */}
          {/* AGENT SYSTEM                                    */}
          {/* ─────────────────────────────────────────────── */}

          <SectionHeading id="agent-overview" level={2}>
            Agent System
          </SectionHeading>

          <p className="text-muted-foreground leading-relaxed mb-4">
            LLMWatch includes a built-in ReAct (Reasoning + Acting) agent that can execute
            multi-step tasks using a set of tools. The agent streams its execution in real time
            via Server-Sent Events (SSE), and every run is automatically traced for debugging
            and analysis.
          </p>

          <div className="glass-card rounded-2xl p-6 my-6">
            <h4 className="font-semibold mb-3">How it works</h4>
            <div className="space-y-3 text-sm text-muted-foreground">
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-primary/15 text-primary flex items-center justify-center shrink-0 text-xs font-semibold">1</span>
                <span>You send a prompt with selected tools and model via <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">POST /agent/run</code>.</span>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-primary/15 text-primary flex items-center justify-center shrink-0 text-xs font-semibold">2</span>
                <span>The agent reasons about the task, selects a tool, executes it, and observes the result.</span>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-primary/15 text-primary flex items-center justify-center shrink-0 text-xs font-semibold">3</span>
                <span>This think → act → observe loop repeats until the agent has a final answer or reaches max iterations.</span>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-primary/15 text-primary flex items-center justify-center shrink-0 text-xs font-semibold">4</span>
                <span>Every step is streamed to the client as an SSE event and stored as a trace.</span>
              </div>
            </div>
          </div>

          {/* Run Agent */}
          <SectionHeading id="agent-run" level={2}>
            Run Agent
          </SectionHeading>

          <div className="flex items-center gap-3 mb-4">
            <MethodBadge method="POST" />
            <code className="text-sm font-mono text-foreground">/agent/run</code>
            <span className="text-xs text-error ml-2">Auth required</span>
            <span className="text-xs text-primary ml-1">SSE stream</span>
          </div>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Executes a ReAct agent and streams execution events in real time. The response
            is a <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">text/event-stream</code> SSE stream.
          </p>

          <h4 className="font-semibold text-sm mb-2">Request body</h4>
          <ParamTable
            params={[
              { name: 'prompt', type: 'string', required: true, description: 'The task or question for the agent. Max 10,000 chars.' },
              { name: 'model', type: '"qwen" | "gemini"', required: true, description: 'LLM model for the agent\'s reasoning.' },
              { name: 'tools', type: 'string[]', required: false, description: 'Tools to enable. Default: all four tools. Options: "web_search", "code_execute", "db_query", "doc_analyze".' },
              { name: 'max_iterations', type: 'integer', required: false, description: 'Max reasoning loops. Default: 10. Range: 1–20.' },
            ]}
          />

          <CodeBlock language="bash" title="Example request">
{`curl -N -X POST http://localhost:8000/agent/run \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "Calculate the factorial of 15 and then search for how factorials are used in probability",
    "model": "gemini",
    "tools": ["code_execute", "web_search"],
    "max_iterations": 10
  }'`}
          </CodeBlock>

          <CodeBlock language="text" title="SSE stream output">
{`data: {"run_id":"abc-123","step_index":0,"event_type":"run_start","content":"Starting agent...","timestamp":"2026-03-07T12:00:00Z"}

data: {"run_id":"abc-123","step_index":1,"event_type":"thinking","content":"I need to calculate 15!...","latency_ms":850,"tokens":45,"timestamp":"2026-03-07T12:00:01Z"}

data: {"run_id":"abc-123","step_index":2,"event_type":"tool_call","content":"Calling execute_python","tool_name":"execute_python","tool_input":"import math\\nprint(math.factorial(15))","timestamp":"2026-03-07T12:00:01Z"}

data: {"run_id":"abc-123","step_index":3,"event_type":"tool_result","content":"1307674368000","tool_name":"execute_python","latency_ms":120,"timestamp":"2026-03-07T12:00:01Z"}

data: {"run_id":"abc-123","step_index":6,"event_type":"final_answer","content":"The factorial of 15 is 1,307,674,368,000...","timestamp":"2026-03-07T12:00:05Z"}

data: {"run_id":"abc-123","step_index":7,"event_type":"run_end","content":"{\"run_id\":\"abc-123\",\"total_steps\":7,\"total_latency_ms\":5200,\"total_tokens\":380,\"total_cost_usd\":0.0015,\"tools_used\":[\"execute_python\",\"web_search\"],\"model_used\":\"gemini\",\"success\":true}","timestamp":"2026-03-07T12:00:05Z"}`}
          </CodeBlock>

          {/* Available Tools */}
          <SectionHeading id="agent-tools" level={2}>
            Available Tools
          </SectionHeading>

          <div className="space-y-4">
            <div className="glass-card rounded-2xl p-6">
              <div className="flex items-center gap-3 mb-3">
                <span className="px-2.5 py-0.5 rounded-md bg-primary/15 text-primary text-xs font-mono font-semibold border border-primary/20">web_search</span>
                <span className="text-sm text-muted-foreground">Web Search</span>
              </div>
              <p className="text-sm text-muted-foreground mb-2">
                Searches the web using DuckDuckGo and returns the top 5 results with titles,
                snippets, and URLs. No API key required.
              </p>
              <div className="text-xs text-muted-foreground/60">
                <strong>Input:</strong> <code className="font-mono">query</code> (string) — The search query.
              </div>
            </div>

            <div className="glass-card rounded-2xl p-6">
              <div className="flex items-center gap-3 mb-3">
                <span className="px-2.5 py-0.5 rounded-md bg-primary/15 text-primary text-xs font-mono font-semibold border border-primary/20">code_execute</span>
                <span className="text-sm text-muted-foreground">Python Code Executor</span>
              </div>
              <p className="text-sm text-muted-foreground mb-2">
                Executes Python code in a sandboxed subprocess with a 15-second timeout
                and stripped environment variables. Code should use <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">print()</code> for output.
              </p>
              <div className="text-xs text-muted-foreground/60">
                <strong>Input:</strong> <code className="font-mono">code</code> (string) — Python code to execute.<br />
                <strong>Limits:</strong> 15s timeout, 10KB max output, sandboxed environment.
              </div>
            </div>

            <div className="glass-card rounded-2xl p-6">
              <div className="flex items-center gap-3 mb-3">
                <span className="px-2.5 py-0.5 rounded-md bg-primary/15 text-primary text-xs font-mono font-semibold border border-primary/20">db_query</span>
                <span className="text-sm text-muted-foreground">LLM Usage Log Query</span>
              </div>
              <p className="text-sm text-muted-foreground mb-2">
                Queries your organization's own LLM usage logs from DynamoDB. Returns cost
                summaries, latency metrics, model breakdowns, and recent log entries. Multi-tenant
                isolated — the agent can only access your company's data.
              </p>
              <div className="text-xs text-muted-foreground/60">
                <strong>Input:</strong> <code className="font-mono">question</code> (string) — Natural language question about your usage.
              </div>
            </div>

            <div className="glass-card rounded-2xl p-6">
              <div className="flex items-center gap-3 mb-3">
                <span className="px-2.5 py-0.5 rounded-md bg-primary/15 text-primary text-xs font-mono font-semibold border border-primary/20">doc_analyze</span>
                <span className="text-sm text-muted-foreground">Document Analyzer</span>
              </div>
              <p className="text-sm text-muted-foreground mb-2">
                Fetches a URL and extracts the visible text content. Handles HTML parsing,
                encoding detection, and content truncation. Useful for analyzing web pages,
                documentation, and articles.
              </p>
              <div className="text-xs text-muted-foreground/60">
                <strong>Input:</strong> <code className="font-mono">url</code> (string) — HTTP/HTTPS URL to fetch.<br />
                <strong>Limits:</strong> 500KB max download, 5,000 chars max returned, 15s timeout.
              </div>
            </div>
          </div>

          {/* SSE Streaming */}
          <SectionHeading id="agent-sse" level={2}>
            SSE Streaming
          </SectionHeading>

          <p className="text-muted-foreground leading-relaxed mb-4">
            The agent endpoint uses Server-Sent Events for real-time streaming. Since the
            standard <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">EventSource</code> API only supports GET requests,
            you need to use <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">fetch()</code> with a <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">ReadableStream</code> for
            POST-based SSE.
          </p>

          <CodeBlock language="typescript" title="Frontend SSE client example">
{`async function streamAgent(token: string, prompt: string) {
  const response = await fetch('/agent/run', {
    method: 'POST',
    headers: {
      'Authorization': \`Bearer \${token}\`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      prompt,
      model: 'gemini',
      tools: ['web_search', 'code_execute'],
    }),
  });

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const event = JSON.parse(line.slice(6));
        console.log(event.event_type, event.content);
      }
    }
  }
}`}
          </CodeBlock>

          <CodeBlock language="python" title="Python SSE client example">
{`import requests
import json

def stream_agent(token: str, prompt: str):
    response = requests.post(
        "http://localhost:8000/agent/run",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "prompt": prompt,
            "model": "gemini",
            "tools": ["web_search", "code_execute"],
        },
        stream=True,
    )

    for line in response.iter_lines():
        if line:
            decoded = line.decode("utf-8")
            if decoded.startswith("data: "):
                event = json.loads(decoded[6:])
                print(f"[{event['event_type']}] {event['content']}")`}
          </CodeBlock>

          {/* ─────────────────────────────────────────────── */}
          {/* TRACING                                         */}
          {/* ─────────────────────────────────────────────── */}

          <SectionHeading id="tracing-overview" level={2}>
            Tracing Overview
          </SectionHeading>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Every agent execution is automatically traced. Traces capture every step — thinking,
            tool calls, tool results, errors, and the final answer — with timestamps, latency,
            token counts, and cost for each step.
          </p>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Traces are stored per-run as a single item in DynamoDB, scoped to your
            organization's <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">company_id</code> for
            multi-tenant isolation.
          </p>

          {/* List Traces */}
          <SectionHeading id="tracing-list" level={2}>
            List Traces
          </SectionHeading>

          <div className="flex items-center gap-3 mb-4">
            <MethodBadge method="GET" />
            <code className="text-sm font-mono text-foreground">/agent/traces</code>
            <span className="text-xs text-error ml-2">Auth required</span>
          </div>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Returns recent agent traces (summary only, without the full step list).
          </p>

          <h4 className="font-semibold text-sm mb-2">Query parameters</h4>
          <ParamTable
            params={[
              { name: 'limit', type: 'integer', required: false, description: 'Max traces to return. Default: 50.' },
            ]}
          />

          <CodeBlock language="json" title="Response — 200 OK">
{`{
  "traces": [
    {
      "run_id": "abc-123-def-456",
      "timestamp": "2026-03-07T12:00:00Z",
      "prompt": "Search the web for AI news",
      "model_used": "gemini",
      "tools_enabled": ["web_search", "doc_analyze"],
      "tools_used": ["web_search"],
      "total_steps": 5,
      "total_latency_ms": 4200.0,
      "total_tokens": 280,
      "total_cost_usd": 0.0012,
      "success": true,
      "final_answer": "Here are the latest AI developments..."
    }
  ]
}`}
          </CodeBlock>

          {/* Trace Detail */}
          <SectionHeading id="tracing-detail" level={2}>
            Trace Detail
          </SectionHeading>

          <div className="flex items-center gap-3 mb-4">
            <MethodBadge method="GET" />
            <code className="text-sm font-mono text-foreground">/agent/traces/:run_id</code>
            <span className="text-xs text-error ml-2">Auth required</span>
          </div>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Returns the full trace for a specific agent run, including all step events.
            Verifies company ownership to prevent cross-tenant access.
          </p>

          <CodeBlock language="json" title="Response — 200 OK (truncated)">
{`{
  "trace": {
    "run_id": "abc-123-def-456",
    "timestamp": "2026-03-07T12:00:00Z",
    "prompt": "Search the web for AI news",
    "model_used": "gemini",
    "total_steps": 5,
    "total_latency_ms": 4200.0,
    "total_tokens": 280,
    "total_cost_usd": 0.0012,
    "success": true,
    "final_answer": "Here are the latest AI developments...",
    "steps": [
      {
        "step_index": 0,
        "event_type": "run_start",
        "content": "Starting agent...",
        "timestamp": "2026-03-07T12:00:00Z"
      },
      {
        "step_index": 1,
        "event_type": "thinking",
        "content": "I should search for recent AI news...",
        "latency_ms": 920,
        "tokens": 45,
        "timestamp": "2026-03-07T12:00:01Z"
      },
      {
        "step_index": 2,
        "event_type": "tool_call",
        "content": "Calling web_search",
        "tool_name": "web_search",
        "tool_input": "latest AI news March 2026",
        "timestamp": "2026-03-07T12:00:01Z"
      }
    ]
  }
}`}
          </CodeBlock>

          {/* Event Types */}
          <SectionHeading id="tracing-events" level={2}>
            Event Types
          </SectionHeading>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Each step in a trace has an <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">event_type</code> that
            describes what happened at that step:
          </p>

          <div className="rounded-xl border border-card-border overflow-hidden my-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-card-border bg-white/[0.02]">
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Event Type</th>
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Description</th>
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Key Fields</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { type: 'run_start', desc: 'Agent execution begins', fields: 'content' },
                  { type: 'thinking', desc: 'LLM reasoning step', fields: 'content, latency_ms, tokens, cost_usd' },
                  { type: 'tool_call', desc: 'Agent invokes a tool', fields: 'content, tool_name, tool_input' },
                  { type: 'tool_result', desc: 'Tool returns output', fields: 'content, tool_name, latency_ms' },
                  { type: 'final_answer', desc: 'Agent produces final response', fields: 'content' },
                  { type: 'error', desc: 'Error during execution', fields: 'content, tool_name (if tool error)' },
                  { type: 'run_end', desc: 'Agent execution complete', fields: 'content (JSON AgentRunSummary)' },
                ].map((e) => (
                  <tr key={e.type} className="border-b border-card-border last:border-0">
                    <td className="px-4 py-2.5">
                      <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">{e.type}</code>
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">{e.desc}</td>
                    <td className="px-4 py-2.5 text-muted-foreground/70 text-xs font-mono">{e.fields}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* ─────────────────────────────────────────────── */}
          {/* ANALYTICS                                       */}
          {/* ─────────────────────────────────────────────── */}

          <SectionHeading id="analytics-overview" level={2}>
            Analytics Overview
          </SectionHeading>

          <p className="text-muted-foreground leading-relaxed mb-4">
            LLMWatch provides two categories of analytics: <strong>LLM Call Analytics</strong> for
            individual chat completion metrics, and <strong>Agent Analytics</strong> for agent
            execution metrics. Both are scoped to your organization.
          </p>

          <div className="glass-card rounded-2xl p-6 my-6">
            <h4 className="font-semibold mb-3">Available analytics endpoints</h4>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-3">
                <MethodBadge method="GET" />
                <code className="font-mono text-xs text-foreground">/analytics/summary</code>
                <span className="text-muted-foreground">— Aggregate KPIs</span>
              </div>
              <div className="flex items-center gap-3">
                <MethodBadge method="GET" />
                <code className="font-mono text-xs text-foreground">/analytics/logs</code>
                <span className="text-muted-foreground">— Raw log entries</span>
              </div>
              <div className="flex items-center gap-3">
                <MethodBadge method="GET" />
                <code className="font-mono text-xs text-foreground">/analytics/timeseries</code>
                <span className="text-muted-foreground">— Chart-ready time series</span>
              </div>
              <div className="flex items-center gap-3">
                <MethodBadge method="GET" />
                <code className="font-mono text-xs text-foreground">/agent/analytics</code>
                <span className="text-muted-foreground">— Agent execution metrics</span>
              </div>
            </div>
          </div>

          {/* Agent Analytics */}
          <SectionHeading id="analytics-agent" level={2}>
            Agent Analytics
          </SectionHeading>

          <div className="flex items-center gap-3 mb-4">
            <MethodBadge method="GET" />
            <code className="text-sm font-mono text-foreground">/agent/analytics</code>
            <span className="text-xs text-error ml-2">Auth required</span>
          </div>

          <p className="text-muted-foreground leading-relaxed mb-4">
            Returns aggregate metrics from up to 200 recent agent executions, including
            success rate, average steps per run, tool usage distribution, and model breakdown.
          </p>

          <CodeBlock language="json" title="Response — 200 OK">
{`{
  "total_runs": 150,
  "success_rate": 94.7,
  "avg_steps": 4.2,
  "avg_latency_ms": 3800.5,
  "total_cost_usd": 0.185432,
  "tool_usage": {
    "web_search": 85,
    "code_execute": 42,
    "db_query": 30,
    "doc_analyze": 15
  },
  "model_breakdown": {
    "gemini": 120,
    "qwen": 30
  }
}`}
          </CodeBlock>

          {/* ─────────────────────────────────────────────── */}
          {/* CONFIGURATION                                   */}
          {/* ─────────────────────────────────────────────── */}

          <SectionHeading id="config-env" level={2}>
            Environment Variables
          </SectionHeading>

          <p className="text-muted-foreground leading-relaxed mb-4">
            All configuration is managed through environment variables loaded from
            a <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">.env</code> file
            in the backend directory. Copy <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">.env.example</code> to
            get started.
          </p>

          <div className="rounded-xl border border-card-border overflow-hidden my-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-card-border bg-white/[0.02]">
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Variable</th>
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Default</th>
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Required</th>
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { name: 'JWT_SECRET_KEY', def: '—', req: true, desc: 'Secret key for signing JWTs. Use: openssl rand -hex 32' },
                  { name: 'JWT_ALGORITHM', def: 'HS256', req: false, desc: 'JWT signing algorithm' },
                  { name: 'JWT_EXPIRE_HOURS', def: '24', req: false, desc: 'Token expiry in hours' },
                  { name: 'GOOGLE_API_KEY', def: '—', req: true, desc: 'Google Gemini API key' },
                  { name: 'QWEN_BASE_URL', def: '—', req: true, desc: 'vLLM endpoint URL for Qwen' },
                  { name: 'QWEN_API_KEY', def: '—', req: true, desc: 'API key for Qwen vLLM endpoint' },
                  { name: 'AWS_REGION', def: '—', req: true, desc: 'AWS region for DynamoDB' },
                  { name: 'AWS_ACCESS_KEY_ID', def: '""', req: false, desc: 'AWS access key (optional with IAM roles)' },
                  { name: 'AWS_SECRET_ACCESS_KEY', def: '""', req: false, desc: 'AWS secret key (optional with IAM roles)' },
                  { name: 'DYNAMODB_TABLE_LOGS', def: '—', req: true, desc: 'DynamoDB table for LLM call logs' },
                  { name: 'DYNAMODB_TABLE_USERS', def: '—', req: true, desc: 'DynamoDB table for user accounts' },
                  { name: 'DYNAMODB_TABLE_TRACES', def: 'llmwatch_traces', req: false, desc: 'DynamoDB table for agent traces' },
                  { name: 'MLFLOW_TRACKING_URI', def: '—', req: true, desc: 'MLFlow tracking server URL' },
                  { name: 'CORS_ORIGINS', def: '—', req: true, desc: 'Comma-separated allowed CORS origins' },
                  { name: 'DEMO_MODE', def: 'true', req: false, desc: 'Enable demo login without database' },
                  { name: 'APP_ENV', def: 'development', req: false, desc: 'Environment: development | production | testing' },
                  { name: 'APP_VERSION', def: '0.1.0', req: false, desc: 'Application version string' },
                ].map((v) => (
                  <tr key={v.name} className="border-b border-card-border last:border-0">
                    <td className="px-4 py-2.5 font-mono text-foreground text-xs">{v.name}</td>
                    <td className="px-4 py-2.5 font-mono text-muted-foreground/70 text-xs">{v.def}</td>
                    <td className="px-4 py-2.5">
                      {v.req ? (
                        <span className="text-error text-xs font-medium">Yes</span>
                      ) : (
                        <span className="text-muted-foreground text-xs">No</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground text-xs">{v.desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <CodeBlock language="env" title="Example .env file">
{`# Authentication
JWT_SECRET_KEY=your-secret-key-generated-with-openssl-rand-hex-32
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=24

# LLM Providers
GOOGLE_API_KEY=your-gemini-api-key
QWEN_BASE_URL=http://your-vllm-endpoint:8080/v1
QWEN_API_KEY=your-qwen-api-key

# AWS / DynamoDB
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
DYNAMODB_TABLE_LOGS=llmwatch_logs
DYNAMODB_TABLE_USERS=llmwatch_users
DYNAMODB_TABLE_TRACES=llmwatch_traces

# MLFlow
MLFLOW_TRACKING_URI=http://localhost:5000

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# App
DEMO_MODE=true
APP_ENV=development
APP_VERSION=0.1.0`}
          </CodeBlock>

          {/* Docker Compose */}
          <SectionHeading id="config-docker" level={2}>
            Docker Compose
          </SectionHeading>

          <p className="text-muted-foreground leading-relaxed mb-4">
            The production stack runs three services via Docker Compose:
          </p>

          <div className="rounded-xl border border-card-border overflow-hidden my-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-card-border bg-white/[0.02]">
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Service</th>
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Port</th>
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Image</th>
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-card-border">
                  <td className="px-4 py-2.5 font-mono text-foreground">backend</td>
                  <td className="px-4 py-2.5 font-mono text-primary/80">8000</td>
                  <td className="px-4 py-2.5 text-muted-foreground text-xs">python:3.11-slim (built)</td>
                  <td className="px-4 py-2.5 text-muted-foreground">FastAPI application server</td>
                </tr>
                <tr className="border-b border-card-border">
                  <td className="px-4 py-2.5 font-mono text-foreground">frontend</td>
                  <td className="px-4 py-2.5 font-mono text-primary/80">3000</td>
                  <td className="px-4 py-2.5 text-muted-foreground text-xs">nginx:alpine (multi-stage)</td>
                  <td className="px-4 py-2.5 text-muted-foreground">React SPA served via Nginx</td>
                </tr>
                <tr>
                  <td className="px-4 py-2.5 font-mono text-foreground">mlflow</td>
                  <td className="px-4 py-2.5 font-mono text-primary/80">5000</td>
                  <td className="px-4 py-2.5 text-muted-foreground text-xs">ghcr.io/mlflow/mlflow:v2.11.1</td>
                  <td className="px-4 py-2.5 text-muted-foreground">Experiment tracking (SQLite backend)</td>
                </tr>
              </tbody>
            </table>
          </div>

          <CodeBlock language="bash" title="Common commands">
{`# Start all services
docker compose up -d

# View logs
docker compose logs -f backend

# Rebuild after code changes
docker compose up -d --build

# Stop everything
docker compose down`}
          </CodeBlock>

          {/* Model Configuration */}
          <SectionHeading id="config-models" level={2}>
            Model Configuration
          </SectionHeading>

          <p className="text-muted-foreground leading-relaxed mb-4">
            LLMWatch uses a Strategy pattern to support multiple LLM providers. Currently
            supported models:
          </p>

          <div className="space-y-4">
            <div className="glass-card rounded-2xl p-6">
              <h4 className="font-semibold mb-2">Gemini (managed)</h4>
              <div className="text-sm text-muted-foreground space-y-1">
                <p><strong>Model:</strong> Gemini 3 Flash</p>
                <p><strong>Provider:</strong> Google Generative AI API</p>
                <p><strong>Config:</strong> Set <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">GOOGLE_API_KEY</code> in your .env</p>
                <p><strong>Thinking mode:</strong> Uses <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">thinking_level="high"</code> when enabled</p>
                <p>
                  <strong>Pricing:</strong> $0.50 / 1M input tokens, $3.00 / 1M output tokens
                </p>
              </div>
            </div>

            <div className="glass-card rounded-2xl p-6">
              <h4 className="font-semibold mb-2">Qwen (self-hosted)</h4>
              <div className="text-sm text-muted-foreground space-y-1">
                <p><strong>Model:</strong> Qwen3.5-35B-A3B</p>
                <p><strong>Provider:</strong> vLLM with OpenAI-compatible API</p>
                <p><strong>Config:</strong> Set <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">QWEN_BASE_URL</code> and <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">QWEN_API_KEY</code> in your .env</p>
                <p><strong>Thinking mode:</strong> Parses <code className="text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded text-xs font-mono">&lt;think&gt;...&lt;/think&gt;</code> tags from response</p>
                <p>
                  <strong>Pricing:</strong> $0.10 / 1M tokens (combined input + output)
                </p>
              </div>
            </div>
          </div>

          {/* ─────────────────────────────────────────────── */}
          {/* Error Responses                                 */}
          {/* ─────────────────────────────────────────────── */}

          <SectionHeading id="error-responses" level={2}>
            Error Responses
          </SectionHeading>

          <p className="text-muted-foreground leading-relaxed mb-4">
            All error responses follow a consistent format with a human-readable message
            and a machine-readable error code:
          </p>

          <CodeBlock language="json" title="Error response format">
{`{
  "error": "Human-readable error message",
  "code": "ERROR_CODE"
}`}
          </CodeBlock>

          <div className="rounded-xl border border-card-border overflow-hidden my-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-card-border bg-white/[0.02]">
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">HTTP Status</th>
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Code</th>
                  <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { status: '400', code: 'VALIDATION_ERROR', desc: 'Invalid request parameters or body' },
                  { status: '401', code: 'AUTHENTICATION_FAILED', desc: 'Missing, invalid, or expired JWT token' },
                  { status: '403', code: 'AUTHORIZATION_FAILED', desc: 'Insufficient permissions' },
                  { status: '404', code: 'RESOURCE_NOT_FOUND', desc: 'Requested resource does not exist' },
                  { status: '500', code: 'LLM_SERVICE_ERROR', desc: 'LLM provider returned an error' },
                  { status: '500', code: 'DATABASE_ERROR', desc: 'DynamoDB operation failed' },
                  { status: '500', code: 'INTERNAL_SERVER_ERROR', desc: 'Unhandled server error' },
                ].map((e) => (
                  <tr key={e.code} className="border-b border-card-border last:border-0">
                    <td className="px-4 py-2.5 font-mono text-foreground">{e.status}</td>
                    <td className="px-4 py-2.5">
                      <code className="text-error/80 bg-error/10 px-1.5 py-0.5 rounded text-xs font-mono">{e.code}</code>
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">{e.desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Bottom spacer */}
          <div className="h-32" />
        </main>
      </div>
    </div>
  );
};

export default Docs;
