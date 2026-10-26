/**
 * Component: Sidebar
 * Purpose: Global navigation: a collapsible rail on desktop, a drawer on mobile.
 */
import React from 'react';
import { NavLink } from 'react-router';
import { ChevronsLeft, ChevronsRight, Zap } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useStore } from '@/store/useStore';
import { NAV_ITEMS } from './nav';

const NavLinks: React.FC<{ expanded: boolean; onNavigate?: () => void }> = ({ expanded, onNavigate }) => (
  <nav className="flex-1 space-y-1 px-3" aria-label="Main">
    {NAV_ITEMS.map(({ name, path, icon: Icon }) => (
      <NavLink
        key={path}
        to={path}
        onClick={onNavigate}
        title={expanded ? undefined : name}
        className={({ isActive }) =>
          cn(
            'relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
            isActive
              ? 'bg-primary/10 text-primary'
              : 'text-muted-foreground hover:bg-white/[0.03] hover:text-foreground',
            !expanded && 'justify-center px-0',
          )
        }
      >
        {({ isActive }) => (
          <>
            {isActive && <span className="absolute inset-y-1 left-0 w-1 rounded-r-md bg-primary" aria-hidden />}
            <Icon size={19} aria-hidden />
            {expanded ? <span>{name}</span> : <span className="sr-only">{name}</span>}
          </>
        )}
      </NavLink>
    ))}
  </nav>
);

const Brand: React.FC<{ expanded: boolean }> = ({ expanded }) => (
  <div className={cn('mb-6 flex items-center gap-3 px-5', !expanded && 'justify-center px-0')}>
    <div className="rounded-xl bg-primary/20 p-2 text-primary glow-effect">
      <Zap size={22} aria-hidden />
    </div>
    {expanded && <span className="text-lg font-bold tracking-tight">LLMWatch</span>}
  </div>
);

/** Desktop rail (hidden below md). */
export const Sidebar: React.FC = () => {
  const { isSidebarOpen, toggleSidebar } = useStore();
  return (
    <aside
      className={cn(
        'hidden md:flex h-screen shrink-0 flex-col border-r border-border bg-card pt-5 pb-4 transition-[width] duration-200',
        isSidebarOpen ? 'w-60' : 'w-[4.5rem]',
      )}
    >
      <Brand expanded={isSidebarOpen} />
      <NavLinks expanded={isSidebarOpen} />
      <div className="px-3">
        <button
          type="button"
          onClick={toggleSidebar}
          className="flex w-full items-center justify-center rounded-xl border border-card-border bg-white/[0.03] py-2.5 text-muted-foreground transition-colors hover:bg-white/[0.08] cursor-pointer"
          aria-label={isSidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          {isSidebarOpen ? <ChevronsLeft size={18} /> : <ChevronsRight size={18} />}
        </button>
      </div>
    </aside>
  );
};

/** Contents of the mobile drawer. */
export const MobileNav: React.FC<{ onNavigate: () => void }> = ({ onNavigate }) => (
  <div className="flex h-full flex-col">
    <Brand expanded />
    <NavLinks expanded onNavigate={onNavigate} />
  </div>
);

export default Sidebar;
