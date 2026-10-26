import React from 'react';
import * as RadixSwitch from '@radix-ui/react-switch';
import { cn } from '@/lib/cn';

interface SwitchProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  id?: string;
  disabled?: boolean;
  'aria-label'?: string;
}

export const Switch: React.FC<SwitchProps> = ({ checked, onCheckedChange, id, disabled, ...rest }) => (
  <RadixSwitch.Root
    id={id}
    checked={checked}
    onCheckedChange={onCheckedChange}
    disabled={disabled}
    aria-label={rest['aria-label']}
    className={cn(
      'relative h-6 w-11 shrink-0 rounded-full border border-card-border transition-colors cursor-pointer disabled:opacity-50',
      checked ? 'bg-primary' : 'bg-white/[0.08]',
    )}
  >
    <RadixSwitch.Thumb
      className={cn(
        'block h-5 w-5 rounded-full bg-white shadow transition-transform',
        checked ? 'translate-x-5' : 'translate-x-0.5',
      )}
    />
  </RadixSwitch.Root>
);
