/**
 * Module: react-router.config.ts
 * Purpose: Optional configuration for React Router v7 Vite plugin if we decide to use framework mode.
 * WHY: Included to satisfy specific architectural requirements and future-proof the scaffolding.
 */
import type { Config } from "@react-router/dev/config";

export default {
  ssr: false,
  appDirectory: "src",
} satisfies Config;
