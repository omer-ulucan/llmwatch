/**
 * Module: useStore.ts
 * Purpose: Global state management using Zustand.
 * WHY: Avoids prop drilling and React Context re-render hell. Stores JWT securely in memory.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { AuthState } from '../types';

interface AppState extends AuthState {
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
}

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      // Auth State
      token: null,
      user: null, // Depending on JWT decoding or an endpoint, usually populated later
      isAuthenticated: false,
      setAuth: (token: string) => set({ token, isAuthenticated: true }),
      logout: () => set({ token: null, user: null, isAuthenticated: false }),
      
      // UI State
      isSidebarOpen: true,
      toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
    }),
    {
      name: 'llmwatch-storage',
      partialize: (state) => ({ token: state.token, isAuthenticated: state.isAuthenticated }),
    }
  )
);
