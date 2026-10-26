import React from 'react';
import { cn } from '@/lib/cn';

const fieldClass =
  'w-full rounded-xl bg-black/30 border border-card-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary/60 focus:ring-2 focus:ring-primary/20 disabled:opacity-50 transition-colors';

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn(fieldClass, 'h-10', className)} {...props} />,
);
Input.displayName = 'Input';

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => <textarea ref={ref} className={cn(fieldClass, 'min-h-24', className)} {...props} />);
Textarea.displayName = 'Textarea';

export const NativeSelect = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <select ref={ref} className={cn(fieldClass, 'h-10 pr-8 appearance-auto', className)} {...props}>
    {children}
  </select>
));
NativeSelect.displayName = 'NativeSelect';

interface FieldProps {
  label: string;
  htmlFor?: string;
  hint?: React.ReactNode;
  error?: string | null;
  children: React.ReactNode;
  className?: string;
}

/** Label + control + hint/error, with accessible wiring left to the caller's ids. */
export const Field: React.FC<FieldProps> = ({ label, htmlFor, hint, error, children, className }) => (
  <div className={cn('space-y-1.5', className)}>
    <label htmlFor={htmlFor} className="block text-sm font-medium text-foreground/90">
      {label}
    </label>
    {children}
    {error ? (
      <p className="text-xs text-error" role="alert">
        {error}
      </p>
    ) : hint ? (
      <p className="text-xs text-muted-foreground">{hint}</p>
    ) : null}
  </div>
);
