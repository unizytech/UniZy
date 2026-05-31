'use client';

/**
 * API Keys Management Screen
 *
 * Allows administrators to:
 * - Create API keys for hospitals (EHR integrations)
 * - Create service tokens for mobile/web apps
 * - View, rotate, and revoke API keys
 * - Monitor usage statistics
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@lib/auth';
import { BACKEND_API_URL } from '@lib/config';
import { authGet, authPost, authPut, authDelete } from '@lib/apiClient';

// Types for API Clients
interface APIClient {
  id: string;
  client_name: string;
  client_type: 'ehr' | 'mobile_app' | 'web_app';
  auth_mode: 'api_key' | 'token';
  api_key_prefix: string | null;
  hospital_id: string | null;
  hospital_name?: string;
  allowed_doctor_ids: string[] | null;
  scopes: string[];
  is_active: boolean;
  rate_limit_per_hour: number;
  token_expiry_minutes: number;
  contact_email: string | null;
  description: string | null;
  created_at: string;
  last_used_at: string | null;
}

interface Hospital {
  id: string;
  hospital_name: string;
  hospital_code: string | null;
  city: string | null;
  state: string | null;
}

interface NewClientForm {
  client_name: string;
  client_type: 'ehr' | 'mobile_app' | 'web_app';
  auth_mode: 'api_key' | 'token';
  hospital_id: string;
  scopes: string[];
  rate_limit_per_hour: number;
  token_expiry_minutes: number;
  contact_email: string;
  description: string;
}

interface EhrType {
  id: string;
  ehr_code: string;
  ehr_name: string;
  default_api_url: string | null;
  description: string | null;
  is_active: boolean;
  created_at: string;
}

interface EhrTypeForm {
  ehr_code: string;
  ehr_name: string;
  default_api_url: string;
  description: string;
}

const DEFAULT_SCOPES = ['read:extractions', 'write:extractions', 'read:patients', 'write:patients'];

export function APIKeysScreen() {
  const { getAccessToken, isSuperAdmin } = useAuth();

  // Tab state
  const [tabMode, setTabMode] = useState<'api-keys' | 'ehr-types'>('api-keys');

  // State
  const [clients, setClients] = useState<APIClient[]>([]);
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // EHR Types state
  const [ehrTypes, setEhrTypes] = useState<EhrType[]>([]);
  const [ehrTypesLoading, setEhrTypesLoading] = useState(false);
  const [showEhrTypeCreateModal, setShowEhrTypeCreateModal] = useState(false);
  const [editingEhrType, setEditingEhrType] = useState<EhrType | null>(null);
  const [ehrTypeForm, setEhrTypeForm] = useState<EhrTypeForm>({ ehr_code: '', ehr_name: '', default_api_url: '', description: '' });
  const [ehrTypeFormError, setEhrTypeFormError] = useState<string | null>(null);
  const [ehrTypeSubmitting, setEhrTypeSubmitting] = useState(false);

  // Edit client state
  const [editingClient, setEditingClient] = useState<APIClient | null>(null);
  const [editClientForm, setEditClientForm] = useState({ rate_limit_per_hour: 1000, token_expiry_minutes: 120 });
  const [editClientError, setEditClientError] = useState<string | null>(null);
  const [editClientSubmitting, setEditClientSubmitting] = useState(false);

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [newApiKey, setNewApiKey] = useState<string | null>(null);
  const [newClientSecret, setNewClientSecret] = useState<string | null>(null);
  const [newClientId, setNewClientId] = useState<string | null>(null);
  const [createdAuthMode, setCreatedAuthMode] = useState<'api_key' | 'token'>('api_key');
  const [createdClientName, setCreatedClientName] = useState<string>('');

  // Form state
  const [formData, setFormData] = useState<NewClientForm>({
    client_name: '',
    client_type: 'ehr',
    auth_mode: 'api_key',
    hospital_id: '',
    scopes: DEFAULT_SCOPES,
    rate_limit_per_hour: 1000,
    token_expiry_minutes: 120,
    contact_email: '',
    description: '',
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Fetch clients - use ref to avoid dependency issues
  const fetchClients = useCallback(async () => {
    try {
      const token = getAccessToken();
      const response = await authGet('/api/v1/admin/clients', token);

      if (!response.ok) {
        throw new Error(`Failed to fetch clients: ${response.statusText}`);
      }

      const data = await response.json();
      setClients(data.clients || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch clients');
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch hospitals
  const fetchHospitals = useCallback(async () => {
    try {
      const token = getAccessToken();
      const response = await authGet('/api/v1/doctors/hospitals', token);

      if (!response.ok) {
        throw new Error(`Failed to fetch hospitals: ${response.statusText}`);
      }

      const data = await response.json();
      setHospitals(data.hospitals || []);
    } catch (err) {
      console.error('Failed to fetch hospitals:', err);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch EHR types
  const fetchEhrTypes = useCallback(async () => {
    try {
      setEhrTypesLoading(true);
      const token = getAccessToken();
      const response = await authGet('/api/v1/hospitals/ehr-types?include_inactive=true', token);

      if (!response.ok) {
        throw new Error(`Failed to fetch EHR types: ${response.statusText}`);
      }

      const data = await response.json();
      setEhrTypes(data.ehr_types || []);
    } catch (err) {
      console.error('Failed to fetch EHR types:', err);
    } finally {
      setEhrTypesLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Initial load - run once on mount
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchClients(), fetchHospitals(), fetchEhrTypes()]);
      setLoading(false);
    };
    loadData();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Create new client
  const handleCreateClient = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    // Validation
    if (!formData.client_name.trim()) {
      setFormError('Client name is required');
      return;
    }

    if (formData.client_type === 'ehr' && !formData.hospital_id) {
      setFormError('Hospital is required for EHR clients');
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await authPost('/api/v1/admin/clients', getAccessToken(), {
        client_name: formData.client_name,
        client_type: formData.client_type,
        auth_mode: formData.client_type === 'ehr' ? formData.auth_mode : 'api_key',
        hospital_id: formData.client_type === 'ehr' ? formData.hospital_id : null,
        scopes: formData.scopes,
        rate_limit_per_hour: formData.rate_limit_per_hour,
        token_expiry_minutes: formData.auth_mode === 'token' ? formData.token_expiry_minutes : 60,
        contact_email: formData.contact_email || null,
        description: formData.description || null,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to create client: ${response.statusText}`);
      }

      const data = await response.json();

      setCreatedClientName(formData.client_name);
      setCreatedAuthMode(data.auth_mode || 'api_key');

      if (data.auth_mode === 'token' && data.client_secret) {
        // Token mode: show client_id + client_secret
        setNewClientId(data.client_id);
        setNewClientSecret(data.client_secret);
        setNewApiKey(null);
        setShowKeyModal(true);
      } else if (data.api_key) {
        // API key mode: show API key
        setNewApiKey(data.api_key);
        setNewClientSecret(null);
        setNewClientId(null);
        setShowKeyModal(true);
      }

      // Reset form and close modal
      setShowCreateModal(false);
      setFormData({
        client_name: '',
        client_type: 'ehr',
        auth_mode: 'api_key',
        token_expiry_minutes: 120,
        hospital_id: '',
        scopes: DEFAULT_SCOPES,
        rate_limit_per_hour: 1000,
        contact_email: '',
        description: '',
      });

      // Refresh client list
      await fetchClients();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to create client');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Rotate API key
  const handleRotateKey = async (clientId: string, clientName: string) => {
    if (!confirm(`Are you sure you want to rotate the API key for "${clientName}"? The old key will stop working immediately.`)) {
      return;
    }

    try {
      const response = await authPost(
        `/api/v1/admin/clients/${clientId}/rotate-key`,
        getAccessToken()
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to rotate key');
      }

      const data = await response.json();

      // Show the new key (rotate endpoint returns 'new_api_key')
      if (data.new_api_key) {
        setNewApiKey(data.new_api_key);
        setCreatedClientName(clientName);
        setShowKeyModal(true);
      }

      await fetchClients();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to rotate key');
    }
  };

  // Deactivate client
  const handleDeactivate = async (clientId: string, clientName: string) => {
    if (!confirm(`Are you sure you want to deactivate "${clientName}"? They will lose API access immediately.`)) {
      return;
    }

    try {
      const response = await authDelete(
        `/api/v1/admin/clients/${clientId}`,
        getAccessToken()
      );

      if (!response.ok) {
        throw new Error('Failed to deactivate client');
      }

      await fetchClients();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to deactivate client');
    }
  };

  // Edit client
  const openEditClient = (client: APIClient) => {
    setEditingClient(client);
    setEditClientForm({
      rate_limit_per_hour: client.rate_limit_per_hour,
      token_expiry_minutes: client.token_expiry_minutes ?? 120,
    });
    setEditClientError(null);
  };

  const handleUpdateClient = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingClient) return;
    setEditClientError(null);
    setEditClientSubmitting(true);

    try {
      const response = await authPut(
        `/api/v1/admin/clients/${editingClient.id}`,
        getAccessToken(),
        {
          rate_limit_per_hour: editClientForm.rate_limit_per_hour,
          token_expiry_minutes: editClientForm.token_expiry_minutes,
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to update client');
      }

      setEditingClient(null);
      await fetchClients();
    } catch (err) {
      setEditClientError(err instanceof Error ? err.message : 'Failed to update client');
    } finally {
      setEditClientSubmitting(false);
    }
  };

  // Switch auth mode (api_key <-> token)
  const handleSwitchAuthMode = async () => {
    if (!editingClient) return;
    const targetMode = editingClient.auth_mode === 'token' ? 'API Key' : 'Token-Based (OAuth)';
    if (!confirm(`Switch "${editingClient.client_name}" to ${targetMode} auth?\n\nThis will generate new credentials and invalidate the old ones immediately.`)) {
      return;
    }

    setEditClientSubmitting(true);
    setEditClientError(null);

    try {
      const response = await authPost(
        `/api/v1/admin/clients/${editingClient.id}/switch-auth-mode`,
        getAccessToken()
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to switch auth mode');
      }

      const data = await response.json();

      // Close edit modal
      setEditingClient(null);

      // Show new credentials
      setCreatedClientName(data.client_name || editingClient.client_name);
      setCreatedAuthMode(data.auth_mode);

      if (data.auth_mode === 'token' && data.client_secret) {
        setNewClientId(data.client_id);
        setNewClientSecret(data.client_secret);
        setNewApiKey(null);
      } else if (data.api_key) {
        setNewApiKey(data.api_key);
        setNewClientSecret(null);
        setNewClientId(null);
      }
      setShowKeyModal(true);

      await fetchClients();
    } catch (err) {
      setEditClientError(err instanceof Error ? err.message : 'Failed to switch auth mode');
    } finally {
      setEditClientSubmitting(false);
    }
  };

  // EHR Type CRUD handlers
  const handleCreateEhrType = async (e: React.FormEvent) => {
    e.preventDefault();
    setEhrTypeFormError(null);

    if (!ehrTypeForm.ehr_code.trim()) {
      setEhrTypeFormError('EHR Code is required');
      return;
    }
    if (!ehrTypeForm.ehr_name.trim()) {
      setEhrTypeFormError('EHR Name is required');
      return;
    }

    setEhrTypeSubmitting(true);
    try {
      const response = await authPost('/api/v1/hospitals/ehr-types', getAccessToken(), {
        ehr_code: ehrTypeForm.ehr_code,
        ehr_name: ehrTypeForm.ehr_name,
        default_api_url: ehrTypeForm.default_api_url || null,
        description: ehrTypeForm.description || null,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to create EHR type: ${response.statusText}`);
      }

      setShowEhrTypeCreateModal(false);
      setEhrTypeForm({ ehr_code: '', ehr_name: '', default_api_url: '', description: '' });
      await fetchEhrTypes();
    } catch (err) {
      setEhrTypeFormError(err instanceof Error ? err.message : 'Failed to create EHR type');
    } finally {
      setEhrTypeSubmitting(false);
    }
  };

  const handleUpdateEhrType = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingEhrType) return;
    setEhrTypeFormError(null);

    if (!ehrTypeForm.ehr_name.trim()) {
      setEhrTypeFormError('EHR Name is required');
      return;
    }

    setEhrTypeSubmitting(true);
    try {
      const response = await authPut(`/api/v1/hospitals/ehr-types/${editingEhrType.id}`, getAccessToken(), {
        ehr_name: ehrTypeForm.ehr_name,
        default_api_url: ehrTypeForm.default_api_url || '',
        description: ehrTypeForm.description || '',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to update EHR type: ${response.statusText}`);
      }

      setEditingEhrType(null);
      setEhrTypeForm({ ehr_code: '', ehr_name: '', default_api_url: '', description: '' });
      await fetchEhrTypes();
    } catch (err) {
      setEhrTypeFormError(err instanceof Error ? err.message : 'Failed to update EHR type');
    } finally {
      setEhrTypeSubmitting(false);
    }
  };

  const handleDeactivateEhrType = async (ehrType: EhrType) => {
    if (!confirm(`Are you sure you want to deactivate "${ehrType.ehr_name}"?`)) return;

    try {
      const response = await authDelete(`/api/v1/hospitals/ehr-types/${ehrType.id}`, getAccessToken());

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to deactivate EHR type');
      }

      await fetchEhrTypes();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to deactivate EHR type');
    }
  };

  const handleReactivateEhrType = async (ehrType: EhrType) => {
    try {
      const response = await authPut(`/api/v1/hospitals/ehr-types/${ehrType.id}`, getAccessToken(), {
        is_active: true,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to reactivate EHR type');
      }

      await fetchEhrTypes();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to reactivate EHR type');
    }
  };

  const openEditEhrType = (ehrType: EhrType) => {
    setEditingEhrType(ehrType);
    setEhrTypeForm({
      ehr_code: ehrType.ehr_code,
      ehr_name: ehrType.ehr_name,
      default_api_url: ehrType.default_api_url || '',
      description: ehrType.description || '',
    });
    setEhrTypeFormError(null);
  };

  // Copy to clipboard
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  // Get hospital name by ID
  const getHospitalName = (hospitalId: string | null) => {
    if (!hospitalId) return 'Global Access';
    const hospital = hospitals.find(h => h.id === hospitalId);
    return hospital?.hospital_name || hospitalId;
  };

  // Format date
  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white">API Keys Management</h2>
          <p className="text-slate-400 text-sm mt-1">
            {tabMode === 'api-keys'
              ? 'Create and manage API keys for school EHR integrations'
              : 'Manage EHR type definitions and their default API URLs'}
          </p>
        </div>
        {tabMode === 'api-keys' ? (
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Create API Key
          </button>
        ) : (
          <button
            onClick={() => {
              setEhrTypeForm({ ehr_code: '', ehr_name: '', default_api_url: '', description: '' });
              setEhrTypeFormError(null);
              setShowEhrTypeCreateModal(true);
            }}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add EHR Type
          </button>
        )}
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 bg-slate-800/50 rounded-lg p-1 border border-slate-700">
        <button
          onClick={() => setTabMode('api-keys')}
          className={`flex-1 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            tabMode === 'api-keys'
              ? 'bg-blue-600 text-white'
              : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
          }`}
        >
          API Key for EHR
        </button>
        <button
          onClick={() => setTabMode('ehr-types')}
          className={`flex-1 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            tabMode === 'ehr-types'
              ? 'bg-blue-600 text-white'
              : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
          }`}
        >
          EHR API URL
        </button>
      </div>

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/50 rounded-lg">
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* === API Keys Tab === */}
      {tabMode === 'api-keys' && (
      <div className="bg-slate-800/50 rounded-xl border border-slate-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-slate-800/80 border-b border-slate-700">
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Client Name</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Type</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Auth</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">School</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Key Prefix</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Status</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Last Used</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {clients.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-400">
                    No API clients found. Create one to get started.
                  </td>
                </tr>
              ) : (
                clients.map((client) => (
                  <tr key={client.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="px-4 py-3">
                      <div>
                        <div className="font-medium text-white">{client.client_name}</div>
                        {client.contact_email && (
                          <div className="text-xs text-slate-400">{client.contact_email}</div>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        client.client_type === 'ehr'
                          ? 'bg-purple-500/20 text-purple-300'
                          : client.client_type === 'mobile_app'
                          ? 'bg-green-500/20 text-green-300'
                          : 'bg-blue-500/20 text-blue-300'
                      }`}>
                        {client.client_type.toUpperCase().replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        client.auth_mode === 'token'
                          ? 'bg-orange-500/20 text-orange-300'
                          : 'bg-slate-500/20 text-slate-300'
                      }`}>
                        {client.auth_mode === 'token' ? 'OAuth Token' : 'API Key'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      {getHospitalName(client.hospital_id)}
                    </td>
                    <td className="px-4 py-3">
                      {client.api_key_prefix ? (
                        <code className="px-2 py-1 bg-slate-900 rounded text-xs text-slate-300">
                          {client.api_key_prefix}...
                        </code>
                      ) : (
                        <span className="text-slate-500 text-sm">JWT Auth</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        client.is_active
                          ? 'bg-green-500/20 text-green-300'
                          : 'bg-red-500/20 text-red-300'
                      }`}>
                        {client.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-400">
                      {formatDate(client.last_used_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {client.is_active && (
                          <button
                            onClick={() => openEditClient(client)}
                            className="p-1.5 text-slate-400 hover:text-blue-400 hover:bg-blue-500/10 rounded transition-colors"
                            title="Edit Settings"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                            </svg>
                          </button>
                        )}
                        {client.client_type === 'ehr' && client.is_active && client.auth_mode !== 'token' && (
                          <button
                            onClick={() => handleRotateKey(client.id, client.client_name)}
                            className="p-1.5 text-slate-400 hover:text-yellow-400 hover:bg-yellow-500/10 rounded transition-colors"
                            title="Rotate API Key"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                          </button>
                        )}
                        {client.is_active && (
                          <button
                            onClick={() => handleDeactivate(client.id, client.client_name)}
                            className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
                            title="Deactivate Client"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                            </svg>
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      )}

      {/* === EHR Types Tab === */}
      {tabMode === 'ehr-types' && (
        <div className="bg-slate-800/50 rounded-xl border border-slate-700 overflow-hidden">
          <div className="overflow-x-auto">
            {ehrTypesLoading ? (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
              </div>
            ) : (
            <table className="w-full">
              <thead>
                <tr className="bg-slate-800/80 border-b border-slate-700">
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">EHR Code</th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">EHR Name</th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Default API URL</th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Description</th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Status</th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-300">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {ehrTypes.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                      No EHR types found. Add one to get started.
                    </td>
                  </tr>
                ) : (
                  ehrTypes.map((ehrType) => (
                    <tr key={ehrType.id} className="hover:bg-slate-800/30 transition-colors">
                      <td className="px-4 py-3">
                        <code className="px-2 py-1 bg-slate-900 rounded text-xs text-slate-300">
                          {ehrType.ehr_code}
                        </code>
                      </td>
                      <td className="px-4 py-3 text-white font-medium">{ehrType.ehr_name}</td>
                      <td className="px-4 py-3 text-sm text-slate-300 max-w-xs truncate">
                        {ehrType.default_api_url || <span className="text-slate-500">-</span>}
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-400 max-w-xs truncate">
                        {ehrType.description || <span className="text-slate-500">-</span>}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${
                          ehrType.is_active
                            ? 'bg-green-500/20 text-green-300'
                            : 'bg-red-500/20 text-red-300'
                        }`}>
                          {ehrType.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => openEditEhrType(ehrType)}
                            className="p-1.5 text-slate-400 hover:text-blue-400 hover:bg-blue-500/10 rounded transition-colors"
                            title="Edit"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                            </svg>
                          </button>
                          {ehrType.is_active ? (
                            <button
                              onClick={() => handleDeactivateEhrType(ehrType)}
                              className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
                              title="Deactivate"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                              </svg>
                            </button>
                          ) : (
                            <button
                              onClick={() => handleReactivateEhrType(ehrType)}
                              className="p-1.5 text-slate-400 hover:text-green-400 hover:bg-green-500/10 rounded transition-colors"
                              title="Reactivate"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                              </svg>
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            )}
          </div>
        </div>
      )}

      {/* Create Client Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-semibold text-white">Create API Client</h3>
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="p-1 text-slate-400 hover:text-white transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <form onSubmit={handleCreateClient} className="space-y-4">
                {/* Client Name */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Client Name *
                  </label>
                  <input
                    type="text"
                    value={formData.client_name}
                    onChange={(e) => setFormData({ ...formData, client_name: e.target.value })}
                    placeholder="e.g., City School EHR"
                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                {/* Client Type */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Client Type *
                  </label>
                  <select
                    value={formData.client_type}
                    onChange={(e) => setFormData({ ...formData, client_type: e.target.value as 'ehr' | 'mobile_app' | 'web_app' })}
                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="ehr">EHR Integration (School-scoped)</option>
                    <option value="mobile_app">Mobile App (Global Access)</option>
                    <option value="web_app">Web App (Global Access)</option>
                  </select>
                  <p className="text-xs text-slate-400 mt-1">
                    {formData.client_type === 'ehr'
                      ? 'EHR clients are restricted to a single school'
                      : 'Mobile/Web apps have access to all schools'}
                  </p>
                </div>

                {/* Auth Mode (for EHR only) */}
                {formData.client_type === 'ehr' && (
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-2">
                      Authentication Mode
                    </label>
                    <div className="flex gap-1 bg-slate-900/50 rounded-lg p-1 border border-slate-600">
                      <button
                        type="button"
                        onClick={() => setFormData({ ...formData, auth_mode: 'api_key' })}
                        className={`flex-1 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                          formData.auth_mode === 'api_key'
                            ? 'bg-blue-600 text-white'
                            : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
                        }`}
                      >
                        API Key (Static)
                      </button>
                      <button
                        type="button"
                        onClick={() => setFormData({ ...formData, auth_mode: 'token' })}
                        className={`flex-1 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                          formData.auth_mode === 'token'
                            ? 'bg-blue-600 text-white'
                            : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
                        }`}
                      >
                        Token-Based (OAuth)
                      </button>
                    </div>
                    <p className="text-xs text-slate-400 mt-1">
                      {formData.auth_mode === 'api_key'
                        ? 'Static API key included in every request. Simple but permanent until rotated.'
                        : 'Short-lived tokens via OAuth 2.0 Client Credentials. EHR exchanges client_id + secret for time-limited access tokens.'}
                    </p>
                  </div>
                )}

                {/* Token Expiry (for token-mode EHR only) */}
                {formData.client_type === 'ehr' && formData.auth_mode === 'token' && (
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Access Token Expiry (minutes)
                    </label>
                    <input
                      type="number"
                      value={formData.token_expiry_minutes}
                      onChange={(e) => setFormData({ ...formData, token_expiry_minutes: parseInt(e.target.value) || 120 })}
                      min={1}
                      max={1440}
                      className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <p className="text-xs text-slate-400 mt-1">
                      How long each access token is valid. Default: 120 min (2 hours). Max: 1440 min (24 hours). Can be changed later without restarting the server.
                    </p>
                  </div>
                )}

                {/* Hospital (for EHR only) */}
                {formData.client_type === 'ehr' && (
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      School *
                    </label>
                    <select
                      value={formData.hospital_id}
                      onChange={(e) => setFormData({ ...formData, hospital_id: e.target.value })}
                      className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="">Select a school</option>
                      {hospitals.map((hospital) => (
                        <option key={hospital.id} value={hospital.id}>
                          {hospital.hospital_name}
                          {hospital.city && ` - ${hospital.city}`}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Rate Limit */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Rate Limit (requests/hour)
                  </label>
                  <input
                    type="number"
                    value={formData.rate_limit_per_hour}
                    onChange={(e) => setFormData({ ...formData, rate_limit_per_hour: parseInt(e.target.value) || 1000 })}
                    min={100}
                    max={10000}
                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                {/* Contact Email */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Contact Email
                  </label>
                  <input
                    type="email"
                    value={formData.contact_email}
                    onChange={(e) => setFormData({ ...formData, contact_email: e.target.value })}
                    placeholder="admin@school.com"
                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                {/* Description */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Description
                  </label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    placeholder="Optional notes about this integration"
                    rows={2}
                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                  />
                </div>

                {/* Error Message */}
                {formError && (
                  <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg">
                    <p className="text-red-400 text-sm">{formError}</p>
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-3 pt-4">
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {isSubmitting ? (
                      <>
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Creating...
                      </>
                    ) : (
                      'Create API Key'
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* API Key / Client Credentials Display Modal (shown once after creation) */}
      {showKeyModal && (newApiKey || newClientSecret) && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-lg w-full">
            <div className="p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-green-500/20 rounded-lg">
                  <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-white">
                    {createdAuthMode === 'token' ? 'OAuth Client Created' : 'API Key Created'}
                  </h3>
                  <p className="text-slate-400 text-sm">for {createdClientName}</p>
                </div>
              </div>

              <div className="bg-yellow-500/10 border border-yellow-500/50 rounded-lg p-3 mb-4">
                <p className="text-yellow-300 text-sm flex items-start gap-2">
                  <svg className="w-5 h-5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <span>
                    <strong>Copy these credentials now!</strong> They will only be shown once for security reasons.
                  </span>
                </p>
              </div>

              {/* Token mode: show client_id + client_secret */}
              {createdAuthMode === 'token' && newClientId && newClientSecret ? (
                <>
                  <div className="space-y-3 mb-4">
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1">Client ID</label>
                      <div className="bg-slate-900 rounded-lg p-3 flex items-center justify-between gap-2">
                        <code className="text-blue-400 text-sm break-all flex-1">{newClientId}</code>
                        <button
                          onClick={() => copyToClipboard(newClientId)}
                          className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded transition-colors flex-shrink-0"
                          title="Copy"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                          </svg>
                        </button>
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1">Client Secret</label>
                      <div className="bg-slate-900 rounded-lg p-3 flex items-center justify-between gap-2">
                        <code className="text-green-400 text-sm break-all flex-1">{newClientSecret}</code>
                        <button
                          onClick={() => copyToClipboard(newClientSecret)}
                          className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded transition-colors flex-shrink-0"
                          title="Copy"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="text-sm text-slate-400 mb-4">
                    <p className="font-medium text-slate-300 mb-2">Usage:</p>
                    <code className="block bg-slate-900 p-2 rounded text-xs whitespace-pre-wrap">{`POST /api/v1/auth/token
Content-Type: application/json

{
  "client_id": "${newClientId}",
  "client_secret": "<secret>",
  "grant_type": "client_credentials"
}`}</code>
                    <p className="text-xs text-slate-500 mt-2">
                      Returns an access_token (1h) + refresh_token (30d). Use the access_token as Bearer token for API calls.
                    </p>
                  </div>
                </>
              ) : (
                <>
                  {/* API Key mode */}
                  <div className="bg-slate-900 rounded-lg p-4 mb-4">
                    <div className="flex items-center justify-between gap-2">
                      <code className="text-green-400 text-sm break-all flex-1">{newApiKey}</code>
                      <button
                        onClick={() => {
                          if (newApiKey) copyToClipboard(newApiKey);
                        }}
                        className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded transition-colors flex-shrink-0"
                        title="Copy to clipboard"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                      </button>
                    </div>
                  </div>

                  <div className="text-sm text-slate-400 mb-4">
                    <p className="font-medium text-slate-300 mb-2">Usage:</p>
                    <code className="block bg-slate-900 p-2 rounded text-xs">
                      Authorization: Bearer {newApiKey}
                    </code>
                  </div>
                </>
              )}

              <button
                onClick={() => {
                  setShowKeyModal(false);
                  setNewApiKey(null);
                  setNewClientSecret(null);
                  setNewClientId(null);
                }}
                className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Client Modal */}
      {editingClient && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h3 className="text-lg font-semibold text-white">Edit Client Settings</h3>
                  <p className="text-slate-400 text-sm mt-1">{editingClient.client_name}</p>
                </div>
                <button
                  onClick={() => setEditingClient(null)}
                  className="p-1 text-slate-400 hover:text-white transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <form onSubmit={handleUpdateClient} className="space-y-4">
                {/* Rate Limit */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Rate Limit (requests/hour)
                  </label>
                  <input
                    type="number"
                    value={editClientForm.rate_limit_per_hour}
                    onChange={(e) => setEditClientForm({ ...editClientForm, rate_limit_per_hour: parseInt(e.target.value) || 1000 })}
                    min={10}
                    max={100000}
                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <p className="text-xs text-slate-400 mt-1">
                    Max API requests allowed per hour. Current: {editingClient.rate_limit_per_hour.toLocaleString()}/hr
                  </p>
                </div>

                {/* Token Expiry (only for token-mode EHR clients) */}
                {editingClient.auth_mode === 'token' && (
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Access Token Expiry (minutes)
                    </label>
                    <input
                      type="number"
                      value={editClientForm.token_expiry_minutes}
                      onChange={(e) => setEditClientForm({ ...editClientForm, token_expiry_minutes: parseInt(e.target.value) || 120 })}
                      min={1}
                      max={1440}
                      className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <p className="text-xs text-slate-400 mt-1">
                      How long each access token is valid (1-1440 min). Takes effect on next token issue — no restart needed.
                    </p>
                  </div>
                )}

                {/* Auth Mode Switch (EHR clients only) */}
                {editingClient.client_type === 'ehr' && (
                  <div className="border border-slate-600 rounded-lg p-4">
                    <label className="block text-sm font-medium text-slate-300 mb-2">
                      Authentication Mode
                    </label>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          editingClient.auth_mode === 'token'
                            ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                            : 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                        }`}>
                          {editingClient.auth_mode === 'token' ? 'OAuth Token' : 'API Key'}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={handleSwitchAuthMode}
                        disabled={editClientSubmitting}
                        className="px-3 py-1.5 text-sm bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/30 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Switch to {editingClient.auth_mode === 'token' ? 'API Key' : 'OAuth Token'}
                      </button>
                    </div>
                    <p className="text-xs text-slate-400 mt-2">
                      Switching generates new credentials and invalidates the old ones immediately.
                    </p>
                  </div>
                )}

                {editClientError && (
                  <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg">
                    <p className="text-red-400 text-sm">{editClientError}</p>
                  </div>
                )}

                <div className="flex gap-3 pt-4">
                  <button
                    type="button"
                    onClick={() => setEditingClient(null)}
                    className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={editClientSubmitting}
                    className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {editClientSubmitting ? (
                      <>
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Saving...
                      </>
                    ) : (
                      'Save Changes'
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Create EHR Type Modal */}
      {showEhrTypeCreateModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-semibold text-white">Add EHR Type</h3>
                <button
                  onClick={() => setShowEhrTypeCreateModal(false)}
                  className="p-1 text-slate-400 hover:text-white transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <form onSubmit={handleCreateEhrType} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">EHR Code *</label>
                  <input
                    type="text"
                    value={ehrTypeForm.ehr_code}
                    onChange={(e) => setEhrTypeForm({ ...ehrTypeForm, ehr_code: e.target.value })}
                    placeholder="e.g., kg_ehr"
                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <p className="text-xs text-slate-400 mt-1">Unique identifier, cannot be changed later</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">EHR Name *</label>
                  <input
                    type="text"
                    value={ehrTypeForm.ehr_name}
                    onChange={(e) => setEhrTypeForm({ ...ehrTypeForm, ehr_name: e.target.value })}
                    placeholder="e.g., KG EHR System"
                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">Default API URL</label>
                  <input
                    type="text"
                    value={ehrTypeForm.default_api_url}
                    onChange={(e) => setEhrTypeForm({ ...ehrTypeForm, default_api_url: e.target.value })}
                    placeholder="https://api.example.com/v1"
                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">Description</label>
                  <textarea
                    value={ehrTypeForm.description}
                    onChange={(e) => setEhrTypeForm({ ...ehrTypeForm, description: e.target.value })}
                    placeholder="Optional description"
                    rows={2}
                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                  />
                </div>

                {ehrTypeFormError && (
                  <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg">
                    <p className="text-red-400 text-sm">{ehrTypeFormError}</p>
                  </div>
                )}

                <div className="flex gap-3 pt-4">
                  <button
                    type="button"
                    onClick={() => setShowEhrTypeCreateModal(false)}
                    className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={ehrTypeSubmitting}
                    className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {ehrTypeSubmitting ? (
                      <>
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Creating...
                      </>
                    ) : (
                      'Create EHR Type'
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Edit EHR Type Modal */}
      {editingEhrType && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-semibold text-white">Edit EHR Type</h3>
                <button
                  onClick={() => setEditingEhrType(null)}
                  className="p-1 text-slate-400 hover:text-white transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <form onSubmit={handleUpdateEhrType} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">EHR Code</label>
                  <input
                    type="text"
                    value={ehrTypeForm.ehr_code}
                    disabled
                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-slate-500 cursor-not-allowed"
                  />
                  <p className="text-xs text-slate-500 mt-1">Cannot be changed</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">EHR Name *</label>
                  <input
                    type="text"
                    value={ehrTypeForm.ehr_name}
                    onChange={(e) => setEhrTypeForm({ ...ehrTypeForm, ehr_name: e.target.value })}
                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">Default API URL</label>
                  <input
                    type="text"
                    value={ehrTypeForm.default_api_url}
                    onChange={(e) => setEhrTypeForm({ ...ehrTypeForm, default_api_url: e.target.value })}
                    placeholder="https://api.example.com/v1"
                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">Description</label>
                  <textarea
                    value={ehrTypeForm.description}
                    onChange={(e) => setEhrTypeForm({ ...ehrTypeForm, description: e.target.value })}
                    placeholder="Optional description"
                    rows={2}
                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                  />
                </div>

                {ehrTypeFormError && (
                  <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg">
                    <p className="text-red-400 text-sm">{ehrTypeFormError}</p>
                  </div>
                )}

                <div className="flex gap-3 pt-4">
                  <button
                    type="button"
                    onClick={() => setEditingEhrType(null)}
                    className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={ehrTypeSubmitting}
                    className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {ehrTypeSubmitting ? (
                      <>
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Saving...
                      </>
                    ) : (
                      'Save Changes'
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default APIKeysScreen;
