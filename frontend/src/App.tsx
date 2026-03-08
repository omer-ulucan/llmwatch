/**
 * Component: App
 * Purpose: Outermost component wrapper initializing the Router.
 * WHY: React Router v7 data API is essential for loaders, actions, and layouts.
 */
import React from 'react';
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router';
import Layout from '@/routes/_layout';
import Home from '@/routes/home';
import Docs from '@/routes/docs';
import Login from '@/routes/login';
import Signup from '@/routes/signup';
import Dashboard from '@/routes/dashboard';
import Chat from '@/routes/chat';
import Analytics from '@/routes/analytics';
import Settings from '@/routes/settings';
import Agent from '@/routes/agent';
import Traces from '@/routes/traces';

const router = createBrowserRouter([
  {
    path: "/",
    element: <Home />,
  },
  {
    path: "/login",
    element: <Login />,
  },
  {
    path: "/signup",
    element: <Signup />,
  },
  {
    path: "/docs",
    element: <Docs />,
  },
  {
    element: <Layout />,
    children: [
      { path: "dashboard", element: <Dashboard /> },
      { path: "chat", element: <Chat /> },
      { path: "agent", element: <Agent /> },
      { path: "traces", element: <Traces /> },
      { path: "analytics", element: <Analytics /> },
      { path: "settings", element: <Settings /> },
    ],
  },
  {
    path: "*",
    element: <Navigate to="/" replace />
  }
]);

const App: React.FC = () => {
  return <RouterProvider router={router} />;
};

export default App;
