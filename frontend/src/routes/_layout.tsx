/**
 * Component: Layout
 * Purpose: App shell: sidebar (rail on desktop, drawer on mobile), navbar, page.
 * WHY: Prevents unmounting and remounting of navigation elements during page transitions.
 */
import React, { Suspense, useState } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router';
import { Sheet, SkeletonRows } from '@/components/ui';
import Navbar from '@/components/Layout/Navbar';
import { MobileNav, Sidebar } from '@/components/Layout/Sidebar';
import { useStore } from '@/store/useStore';

export const PageFallback: React.FC = () => (
  <div className="mx-auto max-w-5xl pt-4">
    <SkeletonRows rows={6} />
  </div>
);

const Layout: React.FC = () => {
  const isAuthenticated = useStore((state) => state.isAuthenticated);
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <Sidebar />
      <Sheet open={menuOpen} onOpenChange={setMenuOpen} title="Navigation" side="left">
        <MobileNav onNavigate={() => setMenuOpen(false)} />
      </Sheet>
      <div className="relative flex h-screen min-w-0 flex-1 flex-col overflow-hidden bg-mesh">
        <Navbar onOpenMenu={() => setMenuOpen(true)} />
        <main className="relative z-0 flex-1 overflow-y-auto overflow-x-hidden p-4 sm:p-6 lg:p-8">
          <Suspense fallback={<PageFallback />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
};

export default Layout;
