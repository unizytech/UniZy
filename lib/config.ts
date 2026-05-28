/**
 * API Configuration
 * Configure the backend API URL based on environment
 */

// Python FastAPI Backend URL
export const BACKEND_API_URL = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';

// API Configuration object
export const API_CONFIG = {
  backendUrl: BACKEND_API_URL,
} as const;

// API Endpoints
export const API_ENDPOINTS = {
  ephemeralToken: `${BACKEND_API_URL}/api/ephemeral-token`,
  liveApiUsage: `${BACKEND_API_URL}/api/live-api-usage`,
  summaryBase: `${BACKEND_API_URL}/api/v1/summary`,
} as const;
