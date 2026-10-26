/**
 * Renders model output as Markdown with syntax-highlighted code.
 * WHY: react-markdown never renders raw HTML (no dangerouslySetInnerHTML), so model
 * output can't inject markup or scripts; links open in a new tab without referrer.
 */
import React, { useState } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github-dark.css';
import { Check, Copy } from 'lucide-react';

const CodeBlock: React.FC<React.HTMLAttributes<HTMLPreElement>> = ({ children, ...props }) => {
  const [copied, setCopied] = useState(false);
  const ref = React.useRef<HTMLPreElement>(null);
  const copy = async () => {
    await navigator.clipboard.writeText(ref.current?.innerText ?? '');
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="group relative my-3">
      <pre ref={ref} {...props} className="overflow-x-auto rounded-xl border border-card-border bg-black/40 p-4 text-[13px] leading-relaxed">
        {children}
      </pre>
      <button
        type="button"
        onClick={() => void copy()}
        className="absolute right-2 top-2 rounded-lg border border-card-border bg-card/80 p-1.5 text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100 focus:opacity-100 cursor-pointer"
        aria-label="Copy code"
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
    </div>
  );
};

const components: Components = {
  pre: ({ node: _node, ...props }) => <CodeBlock {...props} />,
  code: ({ node: _node, className, children, ...props }) =>
    className ? (
      <code className={className} {...props}>
        {children}
      </code>
    ) : (
      <code className="rounded bg-white/[0.08] px-1.5 py-0.5 text-[0.85em]" {...props}>
        {children}
      </code>
    ),
  a: ({ node: _node, ...props }) => (
    <a {...props} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2" />
  ),
  table: ({ node: _node, ...props }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-sm" {...props} />
    </div>
  ),
  th: ({ node: _node, ...props }) => <th className="border border-card-border px-3 py-1.5 text-left" {...props} />,
  td: ({ node: _node, ...props }) => <td className="border border-card-border px-3 py-1.5" {...props} />,
  ul: ({ node: _node, ...props }) => <ul className="my-2 list-disc pl-6" {...props} />,
  ol: ({ node: _node, ...props }) => <ol className="my-2 list-decimal pl-6" {...props} />,
  p: ({ node: _node, ...props }) => <p className="my-2 first:mt-0 last:mb-0" {...props} />,
  h1: ({ node: _node, ...props }) => <h1 className="mb-2 mt-4 text-xl font-semibold" {...props} />,
  h2: ({ node: _node, ...props }) => <h2 className="mb-2 mt-4 text-lg font-semibold" {...props} />,
  h3: ({ node: _node, ...props }) => <h3 className="mb-1 mt-3 font-semibold" {...props} />,
  blockquote: ({ node: _node, ...props }) => (
    <blockquote className="my-2 border-l-2 border-primary/40 pl-3 text-muted-foreground" {...props} />
  ),
};

export const Markdown: React.FC<{ children: string }> = ({ children }) => (
  <div className="break-words text-[15px] leading-relaxed">
    <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]} components={components}>
      {children}
    </ReactMarkdown>
  </div>
);
