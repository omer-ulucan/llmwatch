/**
 * Module: errors.ts
 * Purpose: Extracts a human-readable message from an unknown thrown value.
 * WHY: catch clauses receive `unknown`; this keeps error handling typed instead of using `any`.
 */
import axios from 'axios';

export function getErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError<{ error?: string }>(err)) {
    return err.response?.data?.error || err.message || fallback;
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return fallback;
}
