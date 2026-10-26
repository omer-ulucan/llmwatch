/**
 * Component: App
 * Purpose: Providers (server-state cache, toasts) and the route table.
 * WHY: Every page is lazy-loaded, so the docs page and chart-heavy pages don't
 * inflate the bundle everyone downloads on first load.
 */
import React, { Suspense, lazy } from 'react';
import { Navigate, RouterProvider, createBrowserRouter, useRouteError } from 'react-router';
import { QueryClientProvider } from '@tanstack/react-query';
import { Button, ErrorState, Toaster } from '@/components/ui';
import { queryClient } from '@/lib/query';
import Layout, { PageFallback } from '@/routes/_layout';

const Home = lazy(() => import('@/routes/home'));
const Docs = lazy(() => import('@/routes/docs'));
const Login = lazy(() => import('@/routes/login'));
const Signup = lazy(() => import('@/routes/signup'));
const Dashboard = lazy(() => import('@/routes/dashboard'));
const Chat = lazy(() => import('@/routes/chat'));
const Agent = lazy(() => import('@/routes/agent'));
const Traces = lazy(() => import('@/routes/traces'));
const TraceDetail = lazy(() => import('@/routes/trace-detail'));
const Analytics = lazy(() => import('@/routes/analytics'));
const Settings = lazy(() => import('@/routes/settings'));
const Models = lazy(() => import('@/routes/models'));

const RouteError: React.FC = () => {
  const error = useRouteError();
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center">
      <ErrorState error={error} />
      <Button variant="secondary" onClick={() => window.location.reload()}>
        Reload the page
      </Button>
    </div>
  );
};

const page = (element: React.ReactNode) => (
  <Suspense fallback={<PageFallback />}>{element}</Suspense>
);

const router = createBrowserRouter([
  { path: '/', element: page(<Home />), errorElement: <RouteError /> },
  { path: '/login', element: page(<Login />), errorElement: <RouteError /> },
  { path: '/signup', element: page(<Signup />), errorElement: <RouteError /> },
  { path: '/docs', element: page(<Docs />), errorElement: <RouteError /> },
  {
    element: <Layout />,
    errorElement: <RouteError />,
    children: [
      { path: 'dashboard', element: <Dashboard /> },
      { path: 'chat', element: <Chat /> },
      { path: 'agent', element: <Agent /> },
      { path: 'traces', element: <Traces /> },
      { path: 'traces/:runId', element: <TraceDetail /> },
      { path: 'analytics', element: <Analytics /> },
      { path: 'models', element: <Models /> },
      { path: 'settings', element: <Settings /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]);

const App: React.FC = () => (
  <QueryClientProvider client={queryClient}>
    <RouterProvider router={router} />
    <Toaster />
  </QueryClientProvider>
);

export default App;
