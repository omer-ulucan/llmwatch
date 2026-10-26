import {
  Activity,
  Bot,
  ListTree,
  MessageSquare,
  PieChart,
  Settings,
  type LucideIcon,
} from 'lucide-react';

export interface NavItem {
  name: string;
  path: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { name: 'Dashboard', path: '/dashboard', icon: Activity },
  { name: 'Chat', path: '/chat', icon: MessageSquare },
  { name: 'Agent', path: '/agent', icon: Bot },
  { name: 'Traces', path: '/traces', icon: ListTree },
  { name: 'Analytics', path: '/analytics', icon: PieChart },
  { name: 'Settings', path: '/settings', icon: Settings },
];

/** Title for the current path (longest matching nav prefix). */
export function titleFor(pathname: string): string {
  const match = NAV_ITEMS.filter((i) => pathname === i.path || pathname.startsWith(`${i.path}/`)).sort(
    (a, b) => b.path.length - a.path.length,
  )[0];
  return match?.name ?? 'LLMWatch';
}
