/** Toast notifications (replaces window.alert). Use `toast` from 'sonner'. */
import React from 'react';
import { Toaster as SonnerToaster } from 'sonner';

export const Toaster: React.FC = () => (
  <SonnerToaster
    theme="dark"
    position="bottom-right"
    toastOptions={{
      style: {
        background: 'var(--color-card)',
        border: '1px solid var(--color-card-border)',
        color: 'var(--color-foreground)',
      },
    }}
  />
);
