/**
 * Module: useStore.ts
 * Purpose: Global state management using Zustand.
 * WHY: Avoids prop drilling and React Context re-render hell. Persists the JWT and
 * the sidebar preference to localStorage via the persist middleware.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AuthState } from '../types';

interface AppState extends AuthState {
  /** Desktop sidebar expanded (the mobile drawer is page-local state). */
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
}

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      // Auth State
      token: null,
      user: null,
      isAuthenticated: false,
      setAuth: (token: string) => set({ token, isAuthenticated: true }),
      logout: () => set({ token: null, user: null, isAuthenticated: false }),

      // UI State
      isSidebarOpen: true,
      toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
    }),
    {
      name: 'llmwatch-storage',
      partialize: (state) => ({
        token: state.token,
        isAuthenticated: state.isAuthenticated,
        isSidebarOpen: state.isSidebarOpen,
      }),
    },
  ),
);
