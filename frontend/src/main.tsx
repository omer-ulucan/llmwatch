/**
 * Module: main.tsx
 * Purpose: Application entrypoint.
 * WHY: Bootstraps React 19 concurrent mode rendering.
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
