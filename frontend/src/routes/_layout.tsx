/**
 * Component: Layout (formerly _layout.tsx)
 * Purpose: App shell that houses the Sidebar and Navbar around the router Outlet.
 * WHY: Prevents unmounting and remounting of navigation elements during page transitions.
 */
import React from 'react';
import { Outlet, Navigate, useLocation } from 'react-router';
import Sidebar from '@/components/Layout/Sidebar';
import Navbar from '@/components/Layout/Navbar';
import { useStore } from '@/store/useStore';
import { motion, AnimatePresence } from 'framer-motion';

const Layout: React.FC = () => {
  const isAuthenticated = useStore(state => state.isAuthenticated);
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <Sidebar />
      <div className="flex-1 flex flex-col h-screen overflow-hidden bg-mesh relative">
        <Navbar />
        <main className="flex-1 overflow-y-auto overflow-x-hidden p-8 relative z-0">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
};

export default Layout;
