/**
 * Component: Navbar
 * Purpose: Page title, mobile menu button, and the signed-in user and workspace.
 */
import React from 'react';
import { useLocation, useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { LogOut, Menu } from 'lucide-react';
import { Button } from '@/components/ui';
import { useMe } from '@/hooks/useMe';
import { useStore } from '@/store/useStore';
import { titleFor } from './nav';

const Navbar: React.FC<{ onOpenMenu: () => void }> = ({ onOpenMenu }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logout = useStore((state) => state.logout);
  const { data: me } = useMe();

  const handleLogout = () => {
    logout();
    // WHY: Don't show the previous user's cached data to the next one.
    queryClient.clear();
    navigate('/login');
  };

  const email = me?.user.email ?? '';
  const initial = (email || me?.workspace.name || '?').charAt(0).toUpperCase();

  return (
    <header className="sticky top-0 z-10 flex h-16 w-full items-center justify-between gap-3 border-b border-border bg-background/60 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
      <div className="flex min-w-0 items-center gap-2">
        <Button variant="ghost" size="icon" className="md:hidden" onClick={onOpenMenu} aria-label="Open menu">
          <Menu size={20} />
        </Button>
        <h2 className="truncate text-lg font-semibold tracking-tight sm:text-xl">{titleFor(location.pathname)}</h2>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        {me && (
          <div className="flex items-center gap-3 rounded-full glass-card py-1.5 pl-1.5 pr-3" title={email}>
            <div
              className="flex h-8 w-8 items-center justify-center rounded-full bg-secondary/20 text-sm font-medium text-secondary"
              aria-hidden
            >
              {initial}
            </div>
            <div className="hidden leading-tight sm:block">
              <div className="max-w-48 truncate text-sm font-medium">{email}</div>
              <div className="max-w-48 truncate text-xs text-muted-foreground">
                {me.workspace.name} · {me.user.role}
              </div>
            </div>
          </div>
        )}
        <Button variant="ghost" size="icon" onClick={handleLogout} aria-label="Log out" title="Log out">
          <LogOut size={18} />
        </Button>
      </div>
    </header>
  );
};

export default Navbar;
