/**
 * Component: Home
 * Purpose: Enterprise-grade public landing page shown before authentication.
 * WHY: First impression for prospective customers — communicates trust, scale,
 * and business value rather than implementation details.
 */
import React, { useRef } from 'react';
import { Link } from 'react-router';
import { motion, useInView } from 'framer-motion';
import {
  Zap,
  ArrowRight,
  ChevronRight,
  Activity,
  Bot,
  Eye,
  DollarSign,
  Shield,
  Lock,
  CheckCircle,
  Cloud,
  BarChart3,
  Network,
  Search,
  Timer,
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

const metrics = [
  { value: '10M+', label: 'LLM Calls Tracked' },
  { value: '99.9%', label: 'Uptime SLA' },
  { value: '50%', label: 'Avg Cost Reduction' },
  { value: '<2ms', label: 'Monitoring Overhead' },
];

const capabilities = [
  {
    icon: <Network size={24} />,
    title: 'Unified Model Gateway',
    description:
      'Route requests across any provider from a single endpoint. Swap models instantly with zero code changes and no vendor lock-in.',
  },
  {
    icon: <Bot size={24} />,
    title: 'Agent Orchestration & Control',
    description:
      'Deploy, monitor, and debug autonomous AI agents with full execution tracing. See every decision, tool call, and outcome.',
  },
  {
    icon: <Eye size={24} />,
    title: 'End-to-End Tracing',
    description:
      'Trace every step of every request in real time. Identify bottlenecks, failures, and regressions before they impact users.',
  },
  {
    icon: <DollarSign size={24} />,
    title: 'Cost Intelligence',
    description:
      'Track spend per model, team, and feature. Get anomaly alerts and optimization recommendations to cut your AI bill in half.',
  },
  {
    icon: <BarChart3 size={24} />,
    title: 'Performance Analytics',
    description:
      'Latency percentiles, throughput trends, and error rates across every model. Custom dashboards for every stakeholder.',
  },
  {
    icon: <Shield size={24} />,
    title: 'Security & Compliance',
    description:
      'Multi-tenant data isolation, role-based access control, and audit logging. Built for teams that take governance seriously.',
  },
];

const steps = [
  {
    num: '01',
    icon: <Search size={28} />,
    title: 'Integrate',
    description:
      'Add a single API endpoint to your existing LLM calls. SDKs for Python, TypeScript, and REST. Under five minutes to first trace.',
  },
  {
    num: '02',
    icon: <Activity size={28} />,
    title: 'Observe',
    description:
      'Every request, agent run, and model response is captured automatically. Real-time streaming to your dashboard.',
  },
  {
    num: '03',
    icon: <Timer size={28} />,
    title: 'Optimize',
    description:
      'Use cost analytics and performance data to route smarter, cache effectively, and eliminate waste across your AI stack.',
  },
];

const trustSignals = [
  {
    icon: <Shield size={22} />,
    title: 'SOC 2 Compliant',
    description: 'Enterprise-grade security controls audited annually.',
  },
  {
    icon: <Lock size={22} />,
    title: 'Multi-tenant Isolation',
    description: 'Complete data separation between organizations by default.',
  },
  {
    icon: <CheckCircle size={22} />,
    title: '99.9% Uptime SLA',
    description: 'Backed by a financially guaranteed service level agreement.',
  },
  {
    icon: <Cloud size={22} />,
    title: 'Self-hosted or Cloud',
    description: 'Deploy on our cloud or run entirely within your own infrastructure.',
  },
];

const footerLinks: Record<string, { label: string; href: string; isRoute?: boolean }[]> = {
  Product: [
    { label: 'Platform', href: '#platform' },
    { label: 'Pricing', href: '#' },
    { label: 'Documentation', href: '/docs', isRoute: true },
    { label: 'Changelog', href: '#' },
  ],
  Company: [
    { label: 'About', href: '#' },
    { label: 'Blog', href: '#' },
    { label: 'Careers', href: '#' },
    { label: 'Contact', href: '#' },
  ],
  Legal: [
    { label: 'Privacy Policy', href: '#' },
    { label: 'Terms of Service', href: '#' },
    { label: 'Security', href: '#' },
    { label: 'DPA', href: '#' },
  ],
};

/* ── Component ─────────────────────────────────────────────── */

const Home: React.FC = () => {
  return (
    <div className="min-h-screen bg-background text-foreground font-sans relative overflow-x-hidden">
      {/* ── Navbar ─────────────────────────────────────────── */}
      <nav className="fixed top-0 inset-x-0 z-50 backdrop-blur-xl bg-background/70 border-b border-card-border">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="w-9 h-9 bg-primary/20 text-primary rounded-lg flex items-center justify-center glow-effect group-hover:scale-110 transition-transform">
              <Zap size={20} />
            </div>
            <span className="text-lg font-bold tracking-tight">
              LLM<span className="text-gradient">Watch</span>
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-8 text-sm text-muted-foreground">
            <a href="#platform" className="hover:text-foreground transition-colors">
              Platform
            </a>
            <a href="#solutions" className="hover:text-foreground transition-colors">
              Solutions
            </a>
            <a href="#enterprise" className="hover:text-foreground transition-colors">
              Enterprise
            </a>
            <Link to="/docs" className="hover:text-foreground transition-colors">
              Docs
            </Link>
          </div>

          <div className="flex items-center gap-3">
            <Link
              to="/login"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors hidden sm:block"
            >
              Sign In
            </Link>
            <Link
              to="/signup"
              className="text-sm font-medium bg-gradient-to-r from-primary to-primary-hover text-white px-5 py-2 rounded-xl shadow-[0_0_20px_rgba(59,130,246,0.25)] hover:shadow-[0_0_30px_rgba(59,130,246,0.4)] transition-all duration-300"
            >
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Hero ──────────────────────────────────────────── */}
      <header className="relative pt-32 pb-24 md:pt-44 md:pb-36 bg-mesh overflow-hidden">
        <div className="absolute top-1/4 left-[10%] w-[500px] h-[500px] bg-primary/15 rounded-full blur-[140px] pointer-events-none" />
        <div className="absolute bottom-0 right-[10%] w-[400px] h-[400px] bg-secondary/15 rounded-full blur-[120px] pointer-events-none" />

        <div className="max-w-5xl mx-auto px-6 text-center relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/[0.05] border border-card-border text-xs text-muted-foreground mb-8">
              <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
              Enterprise AI Observability
            </div>

            <h1 className="text-5xl md:text-7xl font-bold tracking-tight leading-[1.1] mb-6">
              Complete Visibility Into{' '}
              <br className="hidden md:block" />
              <span className="text-gradient">Your AI Operations</span>
            </h1>

            <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-10 leading-relaxed">
              Monitor every model call, trace agent executions in real time, and reduce AI costs
              by up to 50% — with enterprise-grade security and compliance built in.
            </p>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link
                to="/login"
                className="inline-flex items-center gap-2 text-base font-medium bg-gradient-to-r from-primary to-primary-hover text-white px-8 py-3.5 rounded-xl shadow-[0_0_30px_rgba(59,130,246,0.35)] hover:shadow-[0_0_40px_rgba(59,130,246,0.55)] transition-all duration-300"
              >
                Start Free Trial
                <ArrowRight size={18} />
              </Link>
              <Link
                to="/login"
                className="inline-flex items-center gap-2 text-base text-muted-foreground hover:text-foreground px-8 py-3.5 rounded-xl border border-card-border hover:border-white/10 transition-all duration-300"
              >
                Book a Demo
                <ChevronRight size={18} />
              </Link>
            </div>
          </motion.div>

          {/* Dashboard preview */}
          <motion.div
            initial={{ opacity: 0, y: 60, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 1, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="mt-20 glass-panel rounded-2xl p-1 max-w-4xl mx-auto"
          >
            <div className="rounded-xl bg-card/80 border border-card-border overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-card-border">
                <div className="flex gap-1.5">
                  <div className="w-3 h-3 rounded-full bg-error/60" />
                  <div className="w-3 h-3 rounded-full bg-warning/60" />
                  <div className="w-3 h-3 rounded-full bg-success/60" />
                </div>
                <div className="flex-1 flex justify-center">
                  <div className="px-4 py-1 rounded-md bg-white/[0.04] text-xs text-muted-foreground">
                    app.llmwatch.ai/dashboard
                  </div>
                </div>
              </div>
              <div className="p-6 space-y-4">
                <div className="grid grid-cols-4 gap-3">
                  {[
                    { label: 'Total Requests', value: '2.4M', change: '+12.3%' },
                    { label: 'P95 Latency', value: '142ms', change: '-8.1%' },
                    { label: 'Monthly Spend', value: '$4,218', change: '-23.5%' },
                    { label: 'Success Rate', value: '99.7%', change: '+0.2%' },
                  ].map((kpi) => (
                    <div
                      key={kpi.label}
                      className="glass-card rounded-xl p-4 flex flex-col gap-1.5"
                    >
                      <span className="text-[11px] text-muted-foreground">{kpi.label}</span>
                      <span className="text-lg font-semibold">{kpi.value}</span>
                      <span className={`text-[10px] font-medium ${kpi.change.startsWith('-') && kpi.label !== 'P95 Latency' ? 'text-error' : 'text-success'}`}>
                        {kpi.change}
                      </span>
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { title: 'Requests / Hour', bars: [40, 55, 65, 45, 70, 85, 60, 75, 90, 80, 65, 72] },
                    { title: 'Cost by Model', bars: [90, 60, 35, 20, 15] },
                    { title: 'Error Rate', bars: [10, 8, 15, 5, 3, 7, 4, 2, 6, 3, 5, 2] },
                  ].map((chart) => (
                    <div key={chart.title} className="glass-card rounded-xl p-4 h-28">
                      <div className="text-[10px] text-muted-foreground mb-3">{chart.title}</div>
                      <div className="flex items-end gap-[3px] h-14">
                        {chart.bars.map((h, j) => (
                          <div
                            key={j}
                            className="flex-1 rounded-sm bg-primary/25"
                            style={{ height: `${h}%` }}
                          />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </header>

      {/* ── Metrics Strip (Social Proof) ──────────────────── */}
      <div className="border-t border-b border-card-border bg-white/[0.01]">
        <div className="max-w-7xl mx-auto px-6 py-12">
          <Section className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {metrics.map((m) => (
              <motion.div key={m.label} variants={fadeUp} className="text-center">
                <div className="text-3xl md:text-4xl font-bold text-gradient mb-1">{m.value}</div>
                <div className="text-sm text-muted-foreground">{m.label}</div>
              </motion.div>
            ))}
          </Section>
        </div>
      </div>

      {/* ── Platform Capabilities ─────────────────────────── */}
      <div id="platform" className="max-w-7xl mx-auto px-6 py-28">
        <Section className="text-center mb-16">
          <motion.p variants={fadeUp} className="text-sm text-primary font-medium mb-3 tracking-wide uppercase">
            Platform
          </motion.p>
          <motion.h2 variants={fadeUp} className="text-3xl md:text-4xl font-bold tracking-tight mb-4">
            One platform for your{' '}
            <span className="text-gradient">entire AI stack</span>
          </motion.h2>
          <motion.p variants={fadeUp} className="text-muted-foreground max-w-xl mx-auto">
            From model gateway to cost optimization, everything you need to operate
            AI at scale with confidence.
          </motion.p>
        </Section>

        <Section className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {capabilities.map((c) => (
            <motion.div
              key={c.title}
              variants={fadeUp}
              className="glass-card rounded-2xl p-7 group"
            >
              <div className="w-12 h-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center mb-5 group-hover:shadow-[0_0_20px_var(--color-primary-glow)] transition-shadow duration-300">
                {c.icon}
              </div>
              <h3 className="text-lg font-semibold mb-2">{c.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{c.description}</p>
            </motion.div>
          ))}
        </Section>
      </div>

      {/* ── How It Works ──────────────────────────────────── */}
      <div id="solutions" className="border-t border-card-border">
        <div className="max-w-7xl mx-auto px-6 py-28">
          <Section className="text-center mb-16">
            <motion.p variants={fadeUp} className="text-sm text-primary font-medium mb-3 tracking-wide uppercase">
              Getting Started
            </motion.p>
            <motion.h2 variants={fadeUp} className="text-3xl md:text-4xl font-bold tracking-tight mb-4">
              Up and running in{' '}
              <span className="text-gradient">minutes, not months</span>
            </motion.h2>
            <motion.p variants={fadeUp} className="text-muted-foreground max-w-xl mx-auto">
              No lengthy onboarding. No infrastructure changes. Add one endpoint and get
              immediate visibility.
            </motion.p>
          </Section>

          <Section className="grid md:grid-cols-3 gap-8 max-w-4xl mx-auto">
            {steps.map((s, i) => (
              <motion.div key={s.num} variants={fadeUp} className="relative text-center group">
                {/* Connector line between steps */}
                {i < steps.length - 1 && (
                  <div className="hidden md:block absolute top-8 left-[60%] w-[calc(100%-20%)] h-px bg-gradient-to-r from-card-border to-transparent" />
                )}
                <div className="w-16 h-16 rounded-2xl bg-white/[0.04] border border-card-border text-primary flex items-center justify-center mx-auto mb-6 group-hover:border-primary/30 group-hover:shadow-[0_0_20px_var(--color-primary-glow)] transition-all duration-300">
                  {s.icon}
                </div>
                <span className="text-[11px] font-mono text-primary/60 mb-2 block tracking-widest">
                  STEP {s.num}
                </span>
                <h3 className="text-xl font-semibold mb-2">{s.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed max-w-xs mx-auto">
                  {s.description}
                </p>
              </motion.div>
            ))}
          </Section>
        </div>
      </div>

      {/* ── Enterprise Trust Signals ──────────────────────── */}
      <div id="enterprise" className="border-t border-card-border bg-white/[0.01]">
        <div className="max-w-7xl mx-auto px-6 py-28">
          <Section className="text-center mb-16">
            <motion.p variants={fadeUp} className="text-sm text-primary font-medium mb-3 tracking-wide uppercase">
              Enterprise
            </motion.p>
            <motion.h2 variants={fadeUp} className="text-3xl md:text-4xl font-bold tracking-tight mb-4">
              Built for{' '}
              <span className="text-gradient">enterprise scale</span>
            </motion.h2>
            <motion.p variants={fadeUp} className="text-muted-foreground max-w-xl mx-auto">
              The security, reliability, and deployment flexibility your organization requires.
            </motion.p>
          </Section>

          <Section className="grid md:grid-cols-2 gap-5 max-w-3xl mx-auto">
            {trustSignals.map((t) => (
              <motion.div
                key={t.title}
                variants={fadeUp}
                className="glass-card rounded-2xl p-6 flex items-start gap-4 group"
              >
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
        <div className="max-w-7xl mx-auto px-6 py-28">
          <Section className="text-center">
            <motion.h2 variants={fadeUp} className="text-3xl md:text-4xl font-bold tracking-tight mb-4">
              Take control of your{' '}
              <span className="text-gradient">AI spend</span>
            </motion.h2>
            <motion.p variants={fadeUp} className="text-muted-foreground max-w-lg mx-auto mb-10">
              Join engineering teams that have reduced their AI costs by 50%
              while gaining complete operational visibility.
            </motion.p>
            <Section className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <motion.div variants={fadeUp}>
                <Link
                  to="/login"
                  className="inline-flex items-center gap-2 text-base font-medium bg-gradient-to-r from-primary to-primary-hover text-white px-8 py-3.5 rounded-xl shadow-[0_0_30px_rgba(59,130,246,0.35)] hover:shadow-[0_0_40px_rgba(59,130,246,0.55)] transition-all duration-300"
                >
                  Start Free Trial
                  <ArrowRight size={18} />
                </Link>
              </motion.div>
              <motion.div variants={fadeUp}>
                <Link
                  to="/login"
                  className="inline-flex items-center gap-2 text-base text-muted-foreground hover:text-foreground px-8 py-3.5 rounded-xl border border-card-border hover:border-white/10 transition-all duration-300"
                >
                  Talk to Sales
                  <ChevronRight size={18} />
                </Link>
              </motion.div>
            </Section>
          </Section>
        </div>
      </div>

      {/* ── Footer ────────────────────────────────────────── */}
      <footer className="border-t border-card-border">
        <div className="max-w-7xl mx-auto px-6 pt-16 pb-8">
          {/* Footer columns */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-10 mb-14">
            {/* Brand column */}
            <div className="col-span-2 md:col-span-1">
              <div className="flex items-center gap-2.5 mb-4">
                <div className="w-8 h-8 bg-primary/20 text-primary rounded-lg flex items-center justify-center">
                  <Zap size={16} />
                </div>
                <span className="font-bold tracking-tight">
                  LLM<span className="text-gradient">Watch</span>
                </span>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Enterprise AI observability and cost intelligence platform.
              </p>
            </div>

            {/* Link columns */}
            {Object.entries(footerLinks).map(([heading, links]) => (
              <div key={heading}>
                <h4 className="text-sm font-semibold mb-4">{heading}</h4>
                <ul className="space-y-2.5">
                  {links.map((link) => (
                    <li key={link.label}>
                      {link.isRoute ? (
                        <Link
                          to={link.href}
                          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                        >
                          {link.label}
                        </Link>
                      ) : (
                        <a
                          href={link.href}
                          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                        >
                          {link.label}
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          {/* Bottom bar */}
          <div className="border-t border-card-border pt-8 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
            <span>&copy; {new Date().getFullYear()} LLMWatch, Inc. All rights reserved.</span>
            <div className="flex items-center gap-6">
              <a href="#" className="hover:text-foreground transition-colors">Privacy</a>
              <a href="#" className="hover:text-foreground transition-colors">Terms</a>
              <a href="#" className="hover:text-foreground transition-colors">Security</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Home;
