/**
 * Module: client.ts
 * Purpose: Configured Axios instance.
 * WHY: Centralizes API requests, automatically injecting JWT tokens and intercepting 401s globally.
 */
import axios from 'axios';
import { useStore } from '../store/useStore';

export const apiClient = axios.create({
  baseURL: 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use((config) => {
  const token = useStore.getState().token;
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useStore.getState().logout();
    }
    return Promise.reject(error);
  }
);
