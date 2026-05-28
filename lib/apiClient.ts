/**
 * API Client Utility
 *
 * Provides authenticated fetch wrapper for backend API calls.
 * Supports:
 * - Bearer token (Supabase JWT or API Key)
 * - All authentication uses Authorization: Bearer header
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';

export { API_BASE_URL };

export interface AuthOptions {
  accessToken?: string | null;
  apiKey?: string | null;
}

export function createAuthHeaders(auth: string | AuthOptions | null): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };

  if (typeof auth === 'string') {
    headers['Authorization'] = `Bearer ${auth}`;
  } else if (auth) {
    // Prefer accessToken (JWT) over apiKey, but both use Bearer auth
    if (auth.accessToken) {
      headers['Authorization'] = `Bearer ${auth.accessToken}`;
    } else if (auth.apiKey) {
      headers['Authorization'] = `Bearer ${auth.apiKey}`;
    }
  }

  return headers;
}

export async function authFetch(
  url: string,
  auth: string | AuthOptions | null,
  options: RequestInit = {}
): Promise<Response> {
  const baseHeaders = createAuthHeaders(auth);

  // If body is FormData, don't set Content-Type (let browser set multipart/form-data with boundary)
  if (options.body instanceof FormData) {
    delete (baseHeaders as Record<string, string>)['Content-Type'];
  }

  const headers = {
    ...baseHeaders,
    ...options.headers,
  };

  return fetch(url, { ...options, headers });
}

export async function authGet(
  endpoint: string,
  auth: string | AuthOptions | null
): Promise<Response> {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
  return authFetch(url, auth);
}

export async function authPost(
  endpoint: string,
  auth: string | AuthOptions | null,
  body?: any
): Promise<Response> {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
  return authFetch(url, auth, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  });
}

export async function authPut(
  endpoint: string,
  auth: string | AuthOptions | null,
  body?: any
): Promise<Response> {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
  return authFetch(url, auth, {
    method: 'PUT',
    body: body ? JSON.stringify(body) : undefined,
  });
}

export async function authDelete(
  endpoint: string,
  auth: string | AuthOptions | null
): Promise<Response> {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
  return authFetch(url, auth, { method: 'DELETE' });
}

export async function authPatch(
  endpoint: string,
  auth: string | AuthOptions | null,
  body?: any
): Promise<Response> {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
  return authFetch(url, auth, {
    method: 'PATCH',
    body: body ? JSON.stringify(body) : undefined,
  });
}

// ============================================================================
// Q&A Engine API
// ============================================================================

import type {
  QAQueryRequest,
  QAQueryResponse,
  SuggestedQuestion,
  QuestionCategory,
  EmbeddingModel
} from './types';

export const qaApi = {
  /**
   * Execute a Q&A query
   */
  async query(
    auth: AuthOptions,
    request: QAQueryRequest
  ): Promise<QAQueryResponse> {
    const response = await authPost('/api/v1/qa/query', auth, request);
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Query failed' }));
      throw new Error(error.detail || 'Query failed');
    }
    return response.json();
  },

  /**
   * Get suggested questions
   */
  async getSuggestedQuestions(
    auth: AuthOptions,
    category?: QuestionCategory
  ): Promise<{ questions: SuggestedQuestion[]; count: number }> {
    const params = category ? `?category=${category}` : '';
    const response = await authGet(`/api/v1/qa/suggested-questions${params}`, auth);
    if (!response.ok) {
      throw new Error('Failed to fetch suggested questions');
    }
    return response.json();
  },

  /**
   * Get query history
   */
  async getHistory(
    auth: AuthOptions,
    limit: number = 20,
    page: number = 1
  ): Promise<{ history: any[]; total_count: number; page: number; page_size: number }> {
    const response = await authGet(`/api/v1/qa/history?limit=${limit}&page=${page}`, auth);
    if (!response.ok) {
      throw new Error('Failed to fetch query history');
    }
    return response.json();
  },

  /**
   * Export results to CSV
   */
  async exportResults(
    auth: AuthOptions,
    query: string,
    results: any[],
    format: 'csv' | 'pdf' = 'csv'
  ): Promise<{ success: boolean; content?: string; filename?: string; error_message?: string }> {
    const response = await authPost('/api/v1/qa/export', auth, {
      query,
      results,
      format
    });
    if (!response.ok) {
      throw new Error('Export failed');
    }
    return response.json();
  },

  /**
   * Get patient visits for temporal/longitudinal queries
   */
  async getPatientVisits(
    auth: AuthOptions,
    patientId: string,
    hospitalId?: string,
    doctorId?: string,
    consultationTypeId?: string,
    limit: number = 20
  ): Promise<{ success: boolean; patient_id: string; visits: any[]; count: number }> {
    const params = new URLSearchParams();
    if (hospitalId) params.append('hospital_id', hospitalId);
    if (doctorId) params.append('doctor_id', doctorId);
    if (consultationTypeId) params.append('consultation_type_id', consultationTypeId);
    params.append('limit', limit.toString());

    const queryString = params.toString() ? `?${params.toString()}` : '';
    const response = await authGet(`/api/v1/qa/patients/${patientId}/visits${queryString}`, auth);
    if (!response.ok) {
      throw new Error('Failed to fetch patient visits');
    }
    return response.json();
  }
};

export const qaSettingsApi = {
  /**
   * Get available embedding models
   */
  async getEmbeddingModels(
    auth: AuthOptions
  ): Promise<{ models: EmbeddingModel[]; count: number }> {
    const response = await authGet('/api/v1/qa/settings/embedding-models', auth);
    if (!response.ok) {
      throw new Error('Failed to fetch embedding models');
    }
    return response.json();
  },

  /**
   * Get current embedding model
   */
  async getCurrentModel(
    auth: AuthOptions,
    hospitalId?: string
  ): Promise<EmbeddingModel> {
    const params = hospitalId ? `?hospital_id=${hospitalId}` : '';
    const response = await authGet(`/api/v1/qa/settings/current-model${params}`, auth);
    if (!response.ok) {
      throw new Error('Failed to fetch current model');
    }
    return response.json();
  },

  /**
   * Set embedding model for hospital (admin only)
   */
  async setEmbeddingModel(
    auth: AuthOptions,
    hospitalId: string,
    modelCode: string
  ): Promise<{ success: boolean; message: string }> {
    const response = await authPost(
      `/api/v1/qa/settings/embedding-model?hospital_id=${hospitalId}`,
      auth,
      { model_code: modelCode }
    );
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to set model' }));
      throw new Error(error.detail || 'Failed to set model');
    }
    return response.json();
  },

  /**
   * Trigger re-embedding (admin only)
   */
  async triggerReembedding(
    auth: AuthOptions,
    hospitalId: string
  ): Promise<{ success: boolean; job_id?: string; message: string }> {
    const response = await authPost('/api/v1/qa/settings/reembed', auth, {
      hospital_id: hospitalId
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to start re-embedding' }));
      throw new Error(error.detail || 'Failed to start re-embedding');
    }
    return response.json();
  }
};
