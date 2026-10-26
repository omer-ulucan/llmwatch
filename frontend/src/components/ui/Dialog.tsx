/**
 * Dialog and Sheet on Radix Dialog: focus trap, Esc to close, labelled for screen
 * readers. Sheet slides in from the side (used for config panels on small screens).
 */
import React from 'react';
import * as RadixDialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { cn } from '@/lib/cn';
import { Button } from './Button';

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

export const Dialog: React.FC<DialogProps> = ({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  className,
}) => (
  <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
    <RadixDialog.Portal>
      <RadixDialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
      <RadixDialog.Content
        className={cn(
          'fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-card-border bg-card p-6 shadow-2xl focus:outline-none max-h-[90vh] overflow-y-auto',
          className,
        )}
      >
        <div className="flex items-start justify-between gap-4">
          <RadixDialog.Title className="text-lg font-semibold tracking-tight">{title}</RadixDialog.Title>
          <RadixDialog.Close asChild>
            <Button variant="ghost" size="icon" aria-label="Close">
              <X size={18} />
            </Button>
          </RadixDialog.Close>
        </div>
        {description ? (
          <RadixDialog.Description className="mt-1 text-sm text-muted-foreground">
            {description}
          </RadixDialog.Description>
        ) : (
          <RadixDialog.Description className="sr-only">{title}</RadixDialog.Description>
        )}
        {children && <div className="mt-5">{children}</div>}
        {footer && <div className="mt-6 flex flex-wrap justify-end gap-2">{footer}</div>}
      </RadixDialog.Content>
    </RadixDialog.Portal>
  </RadixDialog.Root>
);

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  danger?: boolean;
  loading?: boolean;
  children?: React.ReactNode;
  confirmDisabled?: boolean;
}

/** Replaces window.confirm. */
export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  onConfirm,
  danger = false,
  loading = false,
  children,
  confirmDisabled = false,
}) => (
  <Dialog
    open={open}
    onOpenChange={onOpenChange}
    title={title}
    description={description}
    footer={
      <>
        <Button variant="secondary" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button
          variant={danger ? 'danger' : 'primary'}
          onClick={onConfirm}
          loading={loading}
          disabled={confirmDisabled}
        >
          {confirmLabel}
        </Button>
      </>
    }
  >
    {children}
  </Dialog>
);

interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  side?: 'left' | 'right';
  children: React.ReactNode;
}

export const Sheet: React.FC<SheetProps> = ({ open, onOpenChange, title, side = 'right', children }) => (
  <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
    <RadixDialog.Portal>
      <RadixDialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
      <RadixDialog.Content
        className={cn(
          'fixed top-0 bottom-0 z-50 w-[min(22rem,90vw)] bg-card border-card-border shadow-2xl p-5 overflow-y-auto focus:outline-none',
          side === 'right' ? 'right-0 border-l' : 'left-0 border-r',
        )}
      >
        <div className="flex items-center justify-between mb-4">
          <RadixDialog.Title className="text-base font-semibold">{title}</RadixDialog.Title>
          <RadixDialog.Close asChild>
            <Button variant="ghost" size="icon" aria-label="Close">
              <X size={18} />
            </Button>
          </RadixDialog.Close>
        </div>
        <RadixDialog.Description className="sr-only">{title}</RadixDialog.Description>
        {children}
      </RadixDialog.Content>
    </RadixDialog.Portal>
  </RadixDialog.Root>
);
