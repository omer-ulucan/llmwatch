/**
 * Loading, empty and error states, badges and page headers shared by every page.
 */
import React from 'react';
import { AlertTriangle, Inbox, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/cn';
import { getErrorMessage } from '@/api/errors';
import { Button } from './Button';

export const Skeleton: React.FC<{ className?: string }> = ({ className }) => (
  <div className={cn('animate-pulse rounded-lg bg-white/[0.05]', className)} aria-hidden />
);

export const SkeletonRows: React.FC<{ rows?: number; className?: string }> = ({ rows = 5, className }) => (
  <div className={cn('space-y-2', className)} role="status" aria-label="Loading">
    {Array.from({ length: rows }, (_, i) => (
      <Skeleton key={i} className="h-10 w-full" />
    ))}
  </div>
);

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ icon, title, description, action, className }) => (
  <div className={cn('flex flex-col items-center justify-center text-center py-12 px-6', className)}>
    <div className="mb-4 rounded-2xl bg-white/[0.03] p-4 text-muted-foreground">{icon ?? <Inbox size={28} />}</div>
    <h3 className="text-base font-semibold">{title}</h3>
    {description && <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>}
    {action && <div className="mt-5">{action}</div>}
  </div>
);

export const ErrorState: React.FC<{ error: unknown; onRetry?: () => void; className?: string }> = ({
  error,
  onRetry,
  className,
}) => (
  <div
    className={cn('flex flex-col items-center justify-center text-center py-10 px-6', className)}
    role="alert"
  >
    <div className="mb-3 rounded-2xl bg-error/10 p-3 text-error">
      <AlertTriangle size={24} />
    </div>
    <p className="text-sm font-medium">Something went wrong</p>
    <p className="mt-1 max-w-md text-sm text-muted-foreground">{getErrorMessage(error, 'Request failed')}</p>
    {onRetry && (
      <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
        <RefreshCw size={14} /> Try again
      </Button>
    )}
  </div>
);

type Tone = 'neutral' | 'primary' | 'success' | 'error' | 'warning' | 'secondary';

const toneClass: Record<Tone, string> = {
  neutral: 'bg-white/[0.05] text-muted-foreground border-white/[0.06]',
  primary: 'bg-primary/10 text-primary border-primary/20',
  secondary: 'bg-secondary/10 text-secondary border-secondary/20',
  success: 'bg-success-bg text-success border-success/20',
  error: 'bg-error-bg text-error border-error/20',
  warning: 'bg-warning-bg text-warning border-warning/20',
};

export const Badge: React.FC<{ tone?: Tone; className?: string; title?: string; children: React.ReactNode }> = ({
  tone = 'neutral',
  className,
  title,
  children,
}) => (
  <span
    title={title}
    className={cn(
      'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide whitespace-nowrap',
      toneClass[tone],
      className,
    )}
  >
    {children}
  </span>
);

interface PageHeaderProps {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({ title, description, actions }) => (
  <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
    </div>
    {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
  </div>
);

export const Card: React.FC<{ className?: string; children: React.ReactNode }> = ({ className, children }) => (
  <div className={cn('glass-panel rounded-2xl', className)}>{children}</div>
);
