/**
 * Component: App
 * Purpose: Outermost component wrapper initializing the Router.
 * WHY: React Router v7 data API is essential for loaders, actions, and layouts.
 */
import React from 'react';
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router';
import Layout from '@/routes/_layout';
import Login from '@/routes/login';
import Dashboard from '@/routes/dashboard';
import Chat from '@/routes/chat';
import Analytics from '@/routes/analytics';
import Settings from '@/routes/settings';

const router = createBrowserRouter([
  {
    path: "/login",
    element: <Login />,
  },
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: "dashboard", element: <Dashboard /> },
      { path: "chat", element: <Chat /> },
      { path: "analytics", element: <Analytics /> },
      { path: "settings", element: <Settings /> },
    ],
  },
  {
    path: "*",
    element: <Navigate to="/dashboard" replace />
  }
]);

const App: React.FC = () => {
  return <RouterProvider router={router} />;
};

export default App;
