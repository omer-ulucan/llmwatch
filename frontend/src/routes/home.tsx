/**
 * Component: Home
 * Purpose: Public landing page shown before sign-in.
 * WHY: Says what the project is and does, nothing more: every feature listed here
 * exists in this repository, and there are no usage, uptime or savings numbers
 * (public-claims.test.ts enforces that).
 */
import React, { useRef } from 'react';
import { Link } from 'react-router';
import { motion, useInView } from 'framer-motion';
import {
  ArrowRight,
  BarChart3,
  Bot,
  BookOpen,
  Code2,
  DollarSign,
  FlaskConical,
  Github,
  Lock,
  Network,
  Server,
  Shield,
  Terminal,
  Zap,
} from 'lucide-react';

/* ── Animation helpers ─────────────────────────────────────── */

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } },
};

const stagger = {
  visible: { transition: { staggerChildren: 0.1 } },
};

function Section({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: '-60px' });
  return (
    <motion.section
      ref={ref}
      initial="hidden"
      animate={inView ? 'visible' : 'hidden'}
      variants={stagger}
      className={className}
    >
      {children}
    </motion.section>
  );
}

/* ── Data ──────────────────────────────────────────────────── */

const GITHUB_URL = 'https://github.com/omer-ulucan/llmwatch';

const highlights = [
  { value: 'MIT', label: 'Open-source license' },
  { value: '1 command', label: 'docker compose up' },
  { value: 'SQLite', label: 'or Postgres, no other services' },
  { value: 'Any', label: 'OpenAI-compatible provider' },
];

const capabilities = [
  {
    icon: <FlaskConical size={24} />,
    title: 'Evals with real statistics',
    description:
      'Run YAML test suites against several models at once. Comparisons report a paired-bootstrap confidence interval and McNemar\'s test, and say so when there are too few cases to tell.',
  },
  {
    icon: <DollarSign size={24} />,
    title: 'Cost as a first-class axis',
    description:
      'Every call records tokens, latency and cost from your own model prices. Eval runs plot quality against cost per case, so a cheaper model that is just as good is easy to spot.',
  },
  {
    icon: <Network size={24} />,
    title: 'Bring any provider',
    description:
      'OpenAI, Gemini, OpenRouter, Groq, Together, or local Ollama, vLLM and LM Studio. Provider keys are encrypted at rest and never returned by the API.',
  },
  {
    icon: <Bot size={24} />,
    title: 'Agent runs, fully traced',
    description:
      'A tool-using agent (web search, URL fetch, usage queries, optional Python) streams each step live and stores the whole run as a trace with per-step latency and cost.',
  },
  {
    icon: <BarChart3 size={24} />,
    title: 'Usage analytics',
    description:
      'Requests, errors, p50/p95 latency and spend over any window, compared with the previous one. Filter and search every call and export the filtered set as CSV.',
  },
  {
    icon: <Terminal size={24} />,
    title: 'Evals in CI',
    description:
      'The llmwatch CLI runs a suite locally or against your server and exits non-zero on a significant regression against a baseline run.',
  },
];

const steps = [
  {
    num: '01',
    icon: <Server size={28} />,
    title: 'Run it',
    description: 'docker compose up starts the API and UI on one volume. A secret key is generated on first boot.',
  },
  {
    num: '02',
    icon: <Network size={28} />,
    title: 'Add a model',
    description: 'Pick a provider preset, paste a key (or point at Ollama), and discover its models. Set prices to track cost.',
  },
  {
    num: '03',
    icon: <FlaskConical size={28} />,
    title: 'Measure',
    description: 'Chat, run the agent, or write an eval suite and compare models with confidence intervals.',
  },
];

const security = [
  {
    icon: <Lock size={22} />,
    title: 'Workspace isolation',
    description: 'Every query is scoped to the caller\'s workspace, with tests that check one workspace cannot read another.',
  },
  {
    icon: <Shield size={22} />,
    title: 'SSRF protection',
    description: 'URL fetching rejects private, loopback and metadata addresses, re-checks every redirect and pins the vetted IP.',
  },
  {
    icon: <Code2 size={22} />,
    title: 'Code execution off by default',
    description: 'The Python tool only exists when you enable it, and even then it is resource-limited, not a sandbox.',
  },
  {
    icon: <Server size={22} />,
    title: 'Self-hosted',
    description: 'Your prompts, outputs and keys stay in your database. No telemetry is sent anywhere.',
  },
];

const CLI_SAMPLE = `$ llmwatch eval run examples/support-triage.yaml \\
    --model Ollama/qwen3:8b --baseline <run-id> \\
    --fail-on-regression

# exit 0: no significant regression
# exit 1: significantly worse than the baseline
# exit 2: usage or configuration error`;

/* ── Component ─────────────────────────────────────────────── */

const primaryCta =
  'inline-flex items-center gap-2 text-base font-medium bg-gradient-to-r from-primary to-primary-hover text-white px-8 py-3.5 rounded-xl shadow-[0_0_30px_rgba(59,130,246,0.35)] hover:shadow-[0_0_40px_rgba(59,130,246,0.55)] transition-all duration-300';
const secondaryCta =
  'inline-flex items-center gap-2 text-base text-muted-foreground hover:text-foreground px-8 py-3.5 rounded-xl border border-card-border hover:border-white/10 transition-all duration-300';

const SectionTitle: React.FC<{ eyebrow: string; title: React.ReactNode; children?: React.ReactNode }> = ({
  eyebrow,
  title,
  children,
}) => (
  <Section className="text-center mb-16">
    <motion.p variants={fadeUp} className="text-sm text-primary font-medium mb-3 tracking-wide uppercase">
      {eyebrow}
    </motion.p>
    <motion.h2 variants={fadeUp} className="text-3xl md:text-4xl font-bold tracking-tight mb-4">
      {title}
    </motion.h2>
    {children && (
      <motion.p variants={fadeUp} className="text-muted-foreground max-w-xl mx-auto">
        {children}
      </motion.p>
    )}
  </Section>
);

const Home: React.FC = () => {
  return (
    <div className="min-h-screen bg-background text-foreground font-sans relative overflow-x-hidden">
      {/* ── Navbar ─────────────────────────────────────────── */}
      <nav className="fixed top-0 inset-x-0 z-50 backdrop-blur-xl bg-background/70 border-b border-card-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="w-9 h-9 bg-primary/20 text-primary rounded-lg flex items-center justify-center glow-effect group-hover:scale-110 transition-transform">
              <Zap size={20} />
            </div>
            <span className="text-lg font-bold tracking-tight">
              LLM<span className="text-gradient">Watch</span>
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-8 text-sm text-muted-foreground">
            <a href="#features" className="hover:text-foreground transition-colors">
              Features
            </a>
            <a href="#start" className="hover:text-foreground transition-colors">
              Get started
            </a>
            <a href="#security" className="hover:text-foreground transition-colors">
              Security
            </a>
            <Link to="/docs" className="hover:text-foreground transition-colors">
              Docs
            </Link>
            <a href={GITHUB_URL} className="hover:text-foreground transition-colors" target="_blank" rel="noreferrer">
              GitHub
            </a>
          </div>

          <div className="flex items-center gap-3">
            <Link to="/login" className="text-sm text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
              Sign in
            </Link>
            <Link
              to="/signup"
              className="text-sm font-medium bg-gradient-to-r from-primary to-primary-hover text-white px-5 py-2 rounded-xl shadow-[0_0_20px_rgba(59,130,246,0.25)] hover:shadow-[0_0_30px_rgba(59,130,246,0.4)] transition-all duration-300"
            >
              Create account
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Hero ──────────────────────────────────────────── */}
      <header className="relative pt-32 pb-24 md:pt-44 md:pb-32 bg-mesh overflow-hidden">
        <div className="absolute top-1/4 left-[10%] w-[500px] h-[500px] bg-primary/15 rounded-full blur-[140px] pointer-events-none" />
        <div className="absolute bottom-0 right-[10%] w-[400px] h-[400px] bg-secondary/15 rounded-full blur-[120px] pointer-events-none" />

        <div className="max-w-5xl mx-auto px-4 sm:px-6 text-center relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/[0.05] border border-card-border text-xs text-muted-foreground mb-8">
              <span className="w-1.5 h-1.5 rounded-full bg-success" />
              Open-source, self-hosted LLMOps
            </div>

            <h1 className="text-4xl sm:text-5xl md:text-7xl font-bold tracking-tight leading-[1.1] mb-6">
              Know which model is{' '}
              <br className="hidden md:block" />
              <span className="text-gradient">actually better</span>
            </h1>

            <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-10 leading-relaxed">
              Track every LLM call&apos;s latency, tokens and cost, trace agent runs step by step, and compare
              models and prompts with evals that tell you when a difference is real and when it is noise.
            </p>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link to="/signup" className={primaryCta}>
                Get started
                <ArrowRight size={18} />
              </Link>
              <a href={GITHUB_URL} target="_blank" rel="noreferrer" className={secondaryCta}>
                <Github size={18} />
                View on GitHub
              </a>
            </div>
          </motion.div>

          {/* CLI preview */}
          <motion.div
            initial={{ opacity: 0, y: 60, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 1, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="mt-20 glass-panel rounded-2xl p-1 max-w-3xl mx-auto text-left"
          >
            <div className="rounded-xl bg-card/80 border border-card-border overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-card-border">
                <div className="flex gap-1.5">
                  <div className="w-3 h-3 rounded-full bg-error/60" />
                  <div className="w-3 h-3 rounded-full bg-warning/60" />
                  <div className="w-3 h-3 rounded-full bg-success/60" />
                </div>
                <span className="flex-1 text-center text-xs text-muted-foreground">Gate a deploy on an eval</span>
              </div>
              <pre className="overflow-x-auto p-5 text-xs sm:text-sm leading-relaxed text-muted-foreground">
                <code>{CLI_SAMPLE}</code>
              </pre>
            </div>
          </motion.div>
        </div>
      </header>

      {/* ── Highlights ────────────────────────────────────── */}
      <div className="border-t border-b border-card-border bg-white/[0.01]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-12">
          <Section className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {highlights.map((m) => (
              <motion.div key={m.label} variants={fadeUp} className="text-center">
                <div className="text-2xl md:text-3xl font-bold text-gradient mb-1">{m.value}</div>
                <div className="text-sm text-muted-foreground">{m.label}</div>
              </motion.div>
            ))}
          </Section>
        </div>
      </div>

      {/* ── Features ──────────────────────────────────────── */}
      <div id="features" className="max-w-7xl mx-auto px-4 sm:px-6 py-28">
        <SectionTitle
          eyebrow="Features"
          title={
            <>
              Observability and evals <span className="text-gradient">in one place</span>
            </>
          }
        >
          The same model registry powers chat, the agent and evals, so every number is measured the same way.
        </SectionTitle>

        <Section className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {capabilities.map((c) => (
            <motion.div key={c.title} variants={fadeUp} className="glass-card rounded-2xl p-7 group">
              <div className="w-12 h-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center mb-5 group-hover:shadow-[0_0_20px_var(--color-primary-glow)] transition-shadow duration-300">
                {c.icon}
              </div>
              <h3 className="text-lg font-semibold mb-2">{c.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{c.description}</p>
            </motion.div>
          ))}
        </Section>
      </div>

      {/* ── Getting started ───────────────────────────────── */}
      <div id="start" className="border-t border-card-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-28">
          <SectionTitle
            eyebrow="Getting started"
            title={
              <>
                Three steps, <span className="text-gradient">no cloud account</span>
              </>
            }
          />
          <Section className="grid md:grid-cols-3 gap-8 max-w-4xl mx-auto">
            {steps.map((s, i) => (
              <motion.div key={s.num} variants={fadeUp} className="relative text-center group">
                {i < steps.length - 1 && (
                  <div className="hidden md:block absolute top-8 left-[60%] w-[calc(100%-20%)] h-px bg-gradient-to-r from-card-border to-transparent" />
                )}
                <div className="w-16 h-16 rounded-2xl bg-white/[0.04] border border-card-border text-primary flex items-center justify-center mx-auto mb-6 group-hover:border-primary/30 group-hover:shadow-[0_0_20px_var(--color-primary-glow)] transition-all duration-300">
                  {s.icon}
                </div>
                <span className="text-[11px] font-mono text-primary/60 mb-2 block tracking-widest">STEP {s.num}</span>
                <h3 className="text-xl font-semibold mb-2">{s.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed max-w-xs mx-auto">{s.description}</p>
              </motion.div>
            ))}
          </Section>
        </div>
      </div>

      {/* ── Security ──────────────────────────────────────── */}
      <div id="security" className="border-t border-card-border bg-white/[0.01]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-28">
          <SectionTitle
            eyebrow="Security"
            title={
              <>
                Safe defaults, <span className="text-gradient">stated plainly</span>
              </>
            }
          >
            What the code does today. The README&apos;s security notes cover the details and the limits.
          </SectionTitle>
          <Section className="grid md:grid-cols-2 gap-5 max-w-3xl mx-auto">
            {security.map((t) => (
              <motion.div key={t.title} variants={fadeUp} className="glass-card rounded-2xl p-6 flex items-start gap-4 group">
                <div className="w-11 h-11 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0 group-hover:shadow-[0_0_20px_var(--color-primary-glow)] transition-shadow duration-300">
                  {t.icon}
                </div>
                <div>
                  <h3 className="font-semibold mb-1">{t.title}</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">{t.description}</p>
                </div>
              </motion.div>
            ))}
          </Section>
        </div>
      </div>

      {/* ── CTA ───────────────────────────────────────────── */}
      <div className="border-t border-card-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-28">
          <Section className="text-center">
            <motion.h2 variants={fadeUp} className="text-3xl md:text-4xl font-bold tracking-tight mb-4">
              Measure before you <span className="text-gradient">switch models</span>
            </motion.h2>
            <motion.p variants={fadeUp} className="text-muted-foreground max-w-lg mx-auto mb-10">
              Self-host it in a minute, point it at the models you already use, and let the data decide.
            </motion.p>
            <Section className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <motion.div variants={fadeUp}>
                <Link to="/signup" className={primaryCta}>
                  Get started
                  <ArrowRight size={18} />
                </Link>
              </motion.div>
              <motion.div variants={fadeUp}>
                <Link to="/docs" className={secondaryCta}>
                  <BookOpen size={18} />
                  Read the docs
                </Link>
              </motion.div>
            </Section>
          </Section>
        </div>
      </div>

      {/* ── Footer ────────────────────────────────────────── */}
      <footer className="border-t border-card-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-primary/20 text-primary rounded-lg flex items-center justify-center">
              <Zap size={14} />
            </div>
            <span>LLMWatch · MIT licensed</span>
          </div>
          <div className="flex items-center gap-6">
            <Link to="/docs" className="hover:text-foreground transition-colors">
              Docs
            </Link>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="hover:text-foreground transition-colors">
              GitHub
            </a>
            <a href={`${GITHUB_URL}/blob/main/LICENSE`} target="_blank" rel="noreferrer" className="hover:text-foreground transition-colors">
              License
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Home;
