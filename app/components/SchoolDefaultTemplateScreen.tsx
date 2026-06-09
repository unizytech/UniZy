'use client';

/**
 * School Default Template Screen
 *
 * Allows administrators to:
 * - View all schools and their current default template
 * - Set or clear the default template for each school
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@lib/auth';
import { authGet, authPut, authPost, authDelete } from '@lib/apiClient';
import { Template } from '@lib/types';
import QualityMetricsModal from './QualityMetricsModal';

interface School {
  id: string;
  school_name: string;
  school_code: string;
  city?: string;
  state?: string;
  default_template_id?: string | null;
  use_ffmpeg_stitching?: boolean;
  audio_quality_block_threshold?: 'poor' | 'fair' | 'none';
  min_transcript_length?: number;
  max_silence_ratio?: number;
  min_snr_db?: number;
  min_rms_db?: number;
  min_speech_ratio?: number;
  silence_thresh_dbfs?: number;
  min_silence_len_ms?: number;
  silence_padding_ms?: number;
  enable_realtime_subscription?: boolean;
  enable_audio_validation?: boolean;
  enable_early_quality_abort?: boolean;
  early_quality_check_seconds?: number;
}

interface EhrType {
  id: string;
  ehr_code: string;
  ehr_name: string;
  default_api_url: string | null;
  description: string | null;
  is_active: boolean;
}

interface EhrIntegration {
  id: string;
  school_id: string;
  ehr_type_id: string;
  ehr_code: string;
  ehr_name: string;
  api_url: string | null;
  has_api_key: boolean;
  is_enabled: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

interface Counsellor {
  id: string;
  counsellor_name: string;
  ehr_type_id: string | null;
}

export function SchoolDefaultTemplateScreen() {
  const { getAccessToken } = useAuth();

  // State
  const [schools, setSchools] = useState<School[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingSchoolId, setUpdatingSchoolId] = useState<string | null>(null);

  // Search
  const [searchTerm, setSearchTerm] = useState('');

  // Settings panel state
  const [expandedSchoolId, setExpandedSchoolId] = useState<string | null>(null);

  // Quality Metrics modal state
  const [metricsSchoolId, setMetricsSchoolId] = useState<string | null>(null);
  const metricsSchool = schools.find(h => h.id === metricsSchoolId);

  // EHR Types (fetched from API)
  const [ehrTypes, setEhrTypes] = useState<EhrType[]>([]);

  // EHR Integration state
  const [ehrIntegrations, setEhrIntegrations] = useState<Record<string, EhrIntegration[]>>({});
  const [loadingEhrSchoolId, setLoadingEhrSchoolId] = useState<string | null>(null);
  const [editingEhrId, setEditingEhrId] = useState<string | null>(null);
  const [addingEhrSchoolId, setAddingEhrSchoolId] = useState<string | null>(null);
  const [ehrFormData, setEhrFormData] = useState({
    ehr_type_id: '',
    api_url: '',
    api_key: '',
    is_enabled: true,
    is_default: false
  });

  // Counsellor EHR assignment state
  const [schoolCounsellors, setSchoolCounsellors] = useState<Record<string, Counsellor[]>>({});
  const [loadingCounsellorsSchoolId, setLoadingCounsellorsSchoolId] = useState<string | null>(null);
  const [updatingCounsellorId, setUpdatingCounsellorId] = useState<string | null>(null);

  // Fetch schools
  const fetchSchools = useCallback(async () => {
    try {
      const token = getAccessToken();
      const response = await authGet('/api/v1/counsellors/schools', token);

      if (!response.ok) {
        throw new Error(`Failed to fetch schools: ${response.statusText}`);
      }

      const data = await response.json();
      setSchools(data.schools || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch schools');
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch templates
  const fetchTemplates = useCallback(async () => {
    try {
      const token = getAccessToken();
      const response = await authGet('/api/v1/summary/templates?active_only=true', token);

      if (!response.ok) {
        throw new Error(`Failed to fetch templates: ${response.statusText}`);
      }

      const data = await response.json();
      setTemplates(data.templates || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch templates');
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch EHR types from API
  const fetchEhrTypes = useCallback(async () => {
    try {
      const token = getAccessToken();
      const response = await authGet('/api/v1/schools/ehr-types', token);

      if (!response.ok) {
        throw new Error(`Failed to fetch EHR types: ${response.statusText}`);
      }

      const data = await response.json();
      setEhrTypes(data.ehr_types || []);
    } catch (err) {
      console.error('Failed to fetch EHR types:', err);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch counsellors for a school
  const fetchSchoolCounsellors = useCallback(async (schoolId: string) => {
    setLoadingCounsellorsSchoolId(schoolId);
    try {
      const token = getAccessToken();
      const response = await authGet(`/api/v1/counsellors/list-all?school_id=${schoolId}`, token);

      if (!response.ok) {
        throw new Error(`Failed to fetch counsellors: ${response.statusText}`);
      }

      const data = await response.json();
      setSchoolCounsellors(prev => ({
        ...prev,
        [schoolId]: (data.counsellors || []).map((d: { id: string; full_name: string; ehr_type_id?: string | null }) => ({
          id: d.id,
          counsellor_name: d.full_name,
          ehr_type_id: d.ehr_type_id || null
        }))
      }));
    } catch (err) {
      console.error('Failed to fetch counsellors:', err);
    } finally {
      setLoadingCounsellorsSchoolId(null);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Initial load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchSchools(), fetchTemplates(), fetchEhrTypes()]);
      setLoading(false);
    };
    loadData();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch EHR integrations and counsellors when expanding a school row
  useEffect(() => {
    if (expandedSchoolId) {
      if (!ehrIntegrations[expandedSchoolId]) {
        fetchEhrIntegrations(expandedSchoolId);
      }
      if (!schoolCounsellors[expandedSchoolId]) {
        fetchSchoolCounsellors(expandedSchoolId);
      }
    }
  }, [expandedSchoolId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Set default template for school
  const handleSetDefaultTemplate = async (schoolId: string, templateId: string | null) => {
    setUpdatingSchoolId(schoolId);
    try {
      const token = getAccessToken();
      const response = await authPut(
        `/api/v1/schools/${schoolId}/default-template`,
        token,
        { template_id: templateId }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to update default template');
      }

      // Update local state
      setSchools(prev => prev.map(h =>
        h.id === schoolId ? { ...h, default_template_id: templateId } : h
      ));
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update default template');
    } finally {
      setUpdatingSchoolId(null);
    }
  };

  // Update audio quality settings
  const handleUpdateQualitySettings = async (
    schoolId: string,
    settings: {
      audio_quality_block_threshold?: 'poor' | 'fair' | 'none';
      min_transcript_length?: number;
      max_silence_ratio?: number;
      min_snr_db?: number;
      min_rms_db?: number;
      min_speech_ratio?: number;
      silence_thresh_dbfs?: number;
      min_silence_len_ms?: number;
      silence_padding_ms?: number;
      enable_realtime_subscription?: boolean;
      enable_audio_validation?: boolean;
      enable_early_quality_abort?: boolean;
      early_quality_check_seconds?: number;
    }
  ) => {
    setUpdatingSchoolId(schoolId);
    try {
      const token = getAccessToken();
      const response = await authPut(
        `/api/v1/schools/${schoolId}/settings`,
        token,
        settings
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to update quality settings');
      }

      // Update local state
      setSchools(prev => prev.map(h =>
        h.id === schoolId ? { ...h, ...settings } : h
      ));
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update quality settings');
    } finally {
      setUpdatingSchoolId(null);
    }
  };

  // Fetch EHR integrations for a school
  const fetchEhrIntegrations = useCallback(async (schoolId: string) => {
    setLoadingEhrSchoolId(schoolId);
    try {
      const token = getAccessToken();
      const response = await authGet(`/api/v1/schools/${schoolId}/ehr-integrations`, token);

      if (!response.ok) {
        throw new Error(`Failed to fetch EHR integrations: ${response.statusText}`);
      }

      const data = await response.json();
      setEhrIntegrations(prev => ({
        ...prev,
        [schoolId]: data.integrations || []
      }));
    } catch (err) {
      console.error('Failed to fetch EHR integrations:', err);
    } finally {
      setLoadingEhrSchoolId(null);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Create EHR integration
  const handleCreateEhrIntegration = async (schoolId: string) => {
    if (!ehrFormData.ehr_type_id) {
      alert('Please select an EHR type');
      return;
    }

    setUpdatingSchoolId(schoolId);
    try {
      const token = getAccessToken();
      const response = await authPost(
        `/api/v1/schools/${schoolId}/ehr-integrations`,
        token,
        {
          ehr_type_id: ehrFormData.ehr_type_id,
          api_url: ehrFormData.api_url || null,
          api_key: ehrFormData.api_key || null,
          is_enabled: ehrFormData.is_enabled,
          is_default: ehrFormData.is_default
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to create EHR integration');
      }

      // Refresh integrations list
      await fetchEhrIntegrations(schoolId);
      setAddingEhrSchoolId(null);
      setEhrFormData({ ehr_type_id: '', api_url: '', api_key: '', is_enabled: true, is_default: false });
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to create EHR integration');
    } finally {
      setUpdatingSchoolId(null);
    }
  };

  // Update EHR integration
  const handleUpdateEhrIntegration = async (schoolId: string, integrationId: string) => {
    setUpdatingSchoolId(schoolId);
    try {
      const token = getAccessToken();
      const response = await authPut(
        `/api/v1/schools/${schoolId}/ehr-integrations/${integrationId}`,
        token,
        {
          api_url: ehrFormData.api_url || null,
          api_key: ehrFormData.api_key,  // Empty string clears it
          is_enabled: ehrFormData.is_enabled,
          is_default: ehrFormData.is_default
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to update EHR integration');
      }

      // Refresh integrations list
      await fetchEhrIntegrations(schoolId);
      setEditingEhrId(null);
      setEhrFormData({ ehr_type_id: '', api_url: '', api_key: '', is_enabled: true, is_default: false });
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update EHR integration');
    } finally {
      setUpdatingSchoolId(null);
    }
  };

  // Delete EHR integration
  const handleDeleteEhrIntegration = async (schoolId: string, integrationId: string, ehrType: string) => {
    if (!confirm(`Are you sure you want to delete the ${ehrType.toUpperCase()} integration?`)) {
      return;
    }

    setUpdatingSchoolId(schoolId);
    try {
      const token = getAccessToken();
      const response = await authDelete(
        `/api/v1/schools/${schoolId}/ehr-integrations/${integrationId}`,
        token
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to delete EHR integration');
      }

      // Refresh integrations list
      await fetchEhrIntegrations(schoolId);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete EHR integration');
    } finally {
      setUpdatingSchoolId(null);
    }
  };

  // Toggle EHR integration enabled/disabled
  const handleToggleEhrEnabled = async (schoolId: string, integration: EhrIntegration) => {
    setUpdatingSchoolId(schoolId);
    try {
      const token = getAccessToken();
      const response = await authPut(
        `/api/v1/schools/${schoolId}/ehr-integrations/${integration.id}`,
        token,
        { is_enabled: !integration.is_enabled }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to toggle EHR integration');
      }

      // Refresh integrations list
      await fetchEhrIntegrations(schoolId);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to toggle EHR integration');
    } finally {
      setUpdatingSchoolId(null);
    }
  };

  // Start editing an EHR integration
  const startEditingEhr = (integration: EhrIntegration) => {
    setEditingEhrId(integration.id);
    setEhrFormData({
      ehr_type_id: integration.ehr_type_id,
      api_url: integration.api_url || '',
      api_key: '',  // Don't show existing key
      is_enabled: integration.is_enabled,
      is_default: integration.is_default
    });
  };

  // Set EHR integration as default
  const handleSetDefaultEhr = async (schoolId: string, integrationId: string) => {
    setUpdatingSchoolId(schoolId);
    try {
      const token = getAccessToken();
      const response = await authPut(
        `/api/v1/schools/${schoolId}/ehr-integrations/${integrationId}`,
        token,
        { is_default: true }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to set default EHR');
      }

      // Refresh integrations list
      await fetchEhrIntegrations(schoolId);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to set default EHR');
    } finally {
      setUpdatingSchoolId(null);
    }
  };

  // Update counsellor's EHR type
  const handleUpdateCounsellorEhrType = async (schoolId: string, counsellorId: string, ehrTypeId: string | null) => {
    setUpdatingCounsellorId(counsellorId);
    try {
      const token = getAccessToken();
      const response = await authPut(
        `/api/v1/counsellors/${counsellorId}/ehr-type`,
        token,
        { ehr_type_id: ehrTypeId }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to update counsellor EHR type');
      }

      // Update local state
      setSchoolCounsellors(prev => ({
        ...prev,
        [schoolId]: (prev[schoolId] || []).map(d =>
          d.id === counsellorId ? { ...d, ehr_type_id: ehrTypeId } : d
        )
      }));
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update counsellor EHR type');
    } finally {
      setUpdatingCounsellorId(null);
    }
  };

  // Get template name by ID
  const getTemplateName = (templateId: string | null | undefined) => {
    if (!templateId) return null;
    const template = templates.find(t => t.id === templateId);
    return template ? template.template_name : null;
  };

  // Get configured EHR type IDs for a school (to disable in add dropdown)
  const getConfiguredEhrTypeIds = (schoolId: string) => {
    const integrations = ehrIntegrations[schoolId] || [];
    return integrations.map(i => i.ehr_type_id);
  };

  // Get EHR type name by ID
  const getEhrTypeName = (ehrTypeId: string | null) => {
    if (!ehrTypeId) return 'None';
    const ehrType = ehrTypes.find(e => e.id === ehrTypeId);
    return ehrType ? ehrType.ehr_name : 'Unknown';
  };

  // Get configured EHR type IDs for a school (for counsellor assignment dropdown)
  const getSchoolEhrTypeIds = (schoolId: string) => {
    const integrations = ehrIntegrations[schoolId] || [];
    return integrations.filter(i => i.is_enabled).map(i => i.ehr_type_id);
  };

  // Filter schools by search
  const filteredSchools = schools.filter(school =>
    school.school_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    school.school_code.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (school.city && school.city.toLowerCase().includes(searchTerm.toLowerCase()))
  );

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
          <h2 className="text-xl font-bold text-white">School Default Templates</h2>
          <p className="text-slate-400 text-sm mt-1">
            Set default extraction templates for each school. Counsellor-specific defaults take priority.
          </p>
        </div>
      </div>

      {/* Search */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search schools..."
            className="w-full px-4 py-2 pl-10 bg-slate-800/50 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <svg className="absolute left-3 top-2.5 w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <div className="text-sm text-slate-400">
          {filteredSchools.length} school{filteredSchools.length !== 1 ? 's' : ''}
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/50 rounded-lg">
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Schools Table */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full table-fixed">
            <colgroup>
              <col className="w-[16%]" />
              <col className="w-[8%]" />
              <col className="w-[28%]" />
              <col className="w-[11%]" />
              <col className="w-[11%]" />
              <col className="w-[11%]" />
              <col className="w-[9%]" />
            </colgroup>
            <thead>
              <tr className="bg-slate-800/80 border-b border-slate-700">
                <th className="text-left px-3 py-3 text-sm font-medium text-slate-300">School</th>
                <th className="text-left px-3 py-3 text-sm font-medium text-slate-300">Code</th>
                <th className="text-left px-3 py-3 text-sm font-medium text-slate-300">Default Template</th>
                <th className="text-center px-2 py-3 text-sm font-medium text-slate-300">Realtime</th>
                <th className="text-center px-2 py-3 text-sm font-medium text-slate-300">Early Stop</th>
                <th className="text-center px-2 py-3 text-sm font-medium text-slate-300">Audio Val.</th>
                <th className="text-center px-2 py-3 text-sm font-medium text-slate-300">Metrics</th>
                <th className="text-center px-2 py-3 text-sm font-medium text-slate-300">Settings</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {filteredSchools.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-400">
                    {searchTerm ? 'No schools match your search.' : 'No schools found.'}
                  </td>
                </tr>
              ) : (
                filteredSchools.map((school) => (
                  <React.Fragment key={school.id}>
                    <tr className="hover:bg-slate-800/30 transition-colors">
                      <td className="px-3 py-3">
                        <span className="font-medium text-white text-sm truncate block">{school.school_name}</span>
                      </td>
                      <td className="px-3 py-3">
                        <code className="px-1.5 py-0.5 bg-slate-900 rounded text-xs text-slate-300">
                          {school.school_code}
                        </code>
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex items-center gap-1">
                          <select
                            value={school.default_template_id || ''}
                            onChange={(e) => handleSetDefaultTemplate(
                              school.id,
                              e.target.value || null
                            )}
                            disabled={updatingSchoolId === school.id}
                            className="w-full px-2 py-1.5 bg-slate-900/50 border border-slate-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 truncate"
                          >
                            <option value="">No default template</option>
                            {templates.map((template) => (
                              <option key={template.id} value={template.id}>
                                {template.template_name} ({template.template_code})
                              </option>
                            ))}
                          </select>
                          {updatingSchoolId === school.id && (
                            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500"></div>
                          )}
                          {school.default_template_id && updatingSchoolId !== school.id && (
                            <button
                              onClick={() => handleSetDefaultTemplate(school.id, null)}
                              className="p-2 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                              title="Clear default template"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          )}
                        </div>
                      </td>
                      <td className="px-2 py-3 text-center">
                        <button
                          onClick={() => handleUpdateQualitySettings(school.id, {
                            enable_realtime_subscription: !school.enable_realtime_subscription
                          })}
                          disabled={updatingSchoolId === school.id}
                          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-800 disabled:opacity-50 ${
                            school.enable_realtime_subscription ? 'bg-blue-600' : 'bg-slate-600'
                          }`}
                          title={school.enable_realtime_subscription ? 'Realtime subscription enabled' : 'Realtime subscription disabled'}
                        >
                          <span
                            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                              school.enable_realtime_subscription ? 'translate-x-6' : 'translate-x-1'
                            }`}
                          />
                        </button>
                      </td>
                      <td className="px-2 py-3 text-center">
                        <button
                          onClick={() => handleUpdateQualitySettings(school.id, {
                            enable_early_quality_abort: !school.enable_early_quality_abort
                          })}
                          disabled={updatingSchoolId === school.id}
                          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-800 disabled:opacity-50 ${
                            school.enable_early_quality_abort ? 'bg-green-600' : 'bg-slate-600'
                          }`}
                          title={school.enable_early_quality_abort ? 'Early hard-stop on bad audio enabled' : 'Early hard-stop on bad audio disabled'}
                        >
                          <span
                            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                              school.enable_early_quality_abort ? 'translate-x-6' : 'translate-x-1'
                            }`}
                          />
                        </button>
                      </td>
                      <td className="px-2 py-3 text-center">
                        <button
                          onClick={() => handleUpdateQualitySettings(school.id, {
                            enable_audio_validation: !(school.enable_audio_validation !== false)
                          })}
                          disabled={updatingSchoolId === school.id}
                          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-800 disabled:opacity-50 ${
                            school.enable_audio_validation !== false ? 'bg-green-600' : 'bg-slate-600'
                          }`}
                          title={school.enable_audio_validation !== false ? 'Audio validation enabled' : 'Audio validation disabled'}
                        >
                          <span
                            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                              school.enable_audio_validation !== false ? 'translate-x-6' : 'translate-x-1'
                            }`}
                          />
                        </button>
                      </td>
                      <td className="px-2 py-3 text-center">
                        <button
                          onClick={() => setMetricsSchoolId(school.id)}
                          className="text-xs text-teal-600 hover:text-teal-800 font-medium px-2 py-1 rounded hover:bg-teal-50 transition-colors"
                        >
                          Quality Metrics
                        </button>
                      </td>
                      <td className="px-2 py-3 text-center">
                        <button
                          onClick={() => setExpandedSchoolId(
                            expandedSchoolId === school.id ? null : school.id
                          )}
                          className="p-2 text-slate-400 hover:text-blue-400 hover:bg-blue-500/10 rounded-lg transition-colors"
                          title="Audio validation settings"
                        >
                          <svg
                            className={`w-5 h-5 transition-transform ${expandedSchoolId === school.id ? 'rotate-180' : ''}`}
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                    {/* Expanded Settings Row */}
                    {expandedSchoolId === school.id && (
                      <tr className="bg-slate-800/40">
                        <td colSpan={8} className="px-2 py-4 space-y-4 overflow-hidden">
                          {/* Audio Validation Settings */}
                          <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-700">
                            <h4 className="text-sm font-medium text-white mb-4">Audio Validation Settings</h4>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                              {/* Min SNR (dB) */}
                              <div>
                                <label className="block text-xs font-medium text-slate-400 mb-1">
                                  Min SNR (dB): {(school.min_snr_db ?? 10).toFixed(0)}
                                </label>
                                <input
                                  type="range"
                                  min={-10}
                                  max={30}
                                  step={1}
                                  value={school.min_snr_db ?? 10}
                                  onChange={(e) => handleUpdateQualitySettings(school.id, {
                                    min_snr_db: parseFloat(e.target.value)
                                  })}
                                  disabled={updatingSchoolId === school.id}
                                  className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
                                />
                                <p className="text-xs text-slate-500 mt-1">
                                  Block if background noise is too high (lower = more lenient)
                                </p>
                              </div>

                              {/* Min Transcript Length */}
                              <div>
                                <label className="block text-xs font-medium text-slate-400 mb-1">
                                  Min Transcript Length (chars)
                                </label>
                                <input
                                  type="number"
                                  min={0}
                                  max={500}
                                  value={school.min_transcript_length ?? 20}
                                  onChange={(e) => handleUpdateQualitySettings(school.id, {
                                    min_transcript_length: parseInt(e.target.value) || 0
                                  })}
                                  disabled={updatingSchoolId === school.id}
                                  className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                                />
                                <p className="text-xs text-slate-500 mt-1">
                                  Block extraction if transcript is shorter
                                </p>
                              </div>

                              {/* Max Silence Ratio */}
                              <div>
                                <label className="block text-xs font-medium text-slate-400 mb-1">
                                  Max Silence Ratio: {((school.max_silence_ratio ?? 0.9) * 100).toFixed(0)}%
                                </label>
                                <input
                                  type="range"
                                  min={50}
                                  max={100}
                                  value={(school.max_silence_ratio ?? 0.9) * 100}
                                  onChange={(e) => handleUpdateQualitySettings(school.id, {
                                    max_silence_ratio: parseInt(e.target.value) / 100
                                  })}
                                  disabled={updatingSchoolId === school.id}
                                  className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
                                />
                                <p className="text-xs text-slate-500 mt-1">
                                  Block if recording is more than this % silent
                                </p>
                              </div>

                              {/* Min Volume (RMS dB) */}
                              <div>
                                <label className="block text-xs font-medium text-slate-400 mb-1">
                                  Min Volume (dB): {(school.min_rms_db ?? -57).toFixed(0)}
                                </label>
                                <input
                                  type="range"
                                  min={-60}
                                  max={0}
                                  step={1}
                                  value={school.min_rms_db ?? -57}
                                  onChange={(e) => handleUpdateQualitySettings(school.id, {
                                    min_rms_db: parseFloat(e.target.value)
                                  })}
                                  disabled={updatingSchoolId === school.id}
                                  className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
                                />
                                <p className="text-xs text-slate-500 mt-1">
                                  Block if audio volume is too low (lower = more lenient)
                                </p>
                              </div>

                              {/* Min Speech Ratio */}
                              <div>
                                <label className="block text-xs font-medium text-slate-400 mb-1">
                                  Min Speech Ratio: {((school.min_speech_ratio ?? 0.10) * 100).toFixed(0)}%
                                </label>
                                <input
                                  type="range"
                                  min={0}
                                  max={50}
                                  value={(school.min_speech_ratio ?? 0.10) * 100}
                                  onChange={(e) => handleUpdateQualitySettings(school.id, {
                                    min_speech_ratio: parseInt(e.target.value) / 100
                                  })}
                                  disabled={updatingSchoolId === school.id}
                                  className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
                                />
                                <p className="text-xs text-slate-500 mt-1">
                                  Block if less than this % of audio contains speech
                                </p>
                              </div>

                              {/* Early Check Interval (editable only when Early Stop is on) */}
                              <div>
                                <label className="block text-xs font-medium text-slate-400 mb-1">
                                  Early Check Interval (sec)
                                </label>
                                <input
                                  type="number"
                                  min={10}
                                  max={120}
                                  value={school.early_quality_check_seconds ?? 30}
                                  onChange={(e) => handleUpdateQualitySettings(school.id, {
                                    early_quality_check_seconds: Math.min(120, Math.max(10, parseInt(e.target.value) || 30))
                                  })}
                                  disabled={updatingSchoolId === school.id || !school.enable_early_quality_abort}
                                  className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                                />
                                <p className="text-xs text-slate-500 mt-1">
                                  {school.enable_early_quality_abort
                                    ? 'When to check audio and hard-stop if unusable (10-120s)'
                                    : 'Enable the "Early Stop" toggle to edit'}
                                </p>
                              </div>
                            </div>
                          </div>

                          {/* Silence Removal Settings */}
                          <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-700">
                            <h4 className="text-sm font-medium text-white mb-1">Silence Removal Settings</h4>
                            <p className="text-xs text-slate-500 mb-4">Applied to recordings longer than 20 minutes before transcription</p>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                              {/* Silence Threshold (dBFS) */}
                              <div>
                                <label className="block text-xs font-medium text-slate-400 mb-1">
                                  Silence Threshold (dBFS): {(school.silence_thresh_dbfs ?? -57).toFixed(0)}
                                </label>
                                <input
                                  type="range"
                                  min={-80}
                                  max={-20}
                                  step={1}
                                  value={school.silence_thresh_dbfs ?? -57}
                                  onChange={(e) => handleUpdateQualitySettings(school.id, {
                                    silence_thresh_dbfs: parseFloat(e.target.value)
                                  })}
                                  disabled={updatingSchoolId === school.id}
                                  className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
                                />
                                <p className="text-xs text-slate-500 mt-1">
                                  Volume below this is silence (lower = more lenient)
                                </p>
                              </div>

                              {/* Min Silence Length (ms) */}
                              <div>
                                <label className="block text-xs font-medium text-slate-400 mb-1">
                                  Min Silence Length: {((school.min_silence_len_ms ?? 5000) / 1000).toFixed(1)}s
                                </label>
                                <input
                                  type="range"
                                  min={500}
                                  max={30000}
                                  step={500}
                                  value={school.min_silence_len_ms ?? 5000}
                                  onChange={(e) => handleUpdateQualitySettings(school.id, {
                                    min_silence_len_ms: parseInt(e.target.value)
                                  })}
                                  disabled={updatingSchoolId === school.id}
                                  className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
                                />
                                <p className="text-xs text-slate-500 mt-1">
                                  Only remove silence gaps longer than this
                                </p>
                              </div>

                              {/* Silence Padding (ms) */}
                              <div>
                                <label className="block text-xs font-medium text-slate-400 mb-1">
                                  Speech Padding: {(school.silence_padding_ms ?? 200)}ms
                                </label>
                                <input
                                  type="range"
                                  min={0}
                                  max={2000}
                                  step={50}
                                  value={school.silence_padding_ms ?? 200}
                                  onChange={(e) => handleUpdateQualitySettings(school.id, {
                                    silence_padding_ms: parseInt(e.target.value)
                                  })}
                                  disabled={updatingSchoolId === school.id}
                                  className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
                                />
                                <p className="text-xs text-slate-500 mt-1">
                                  Padding kept around each speech segment
                                </p>
                              </div>
                            </div>
                          </div>

                          {/* EHR Integrations */}
                          <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-700">
                            <div className="flex items-center justify-between mb-4">
                              <h4 className="text-sm font-medium text-white">EHR Integrations</h4>
                              {!addingEhrSchoolId && (
                                <button
                                  onClick={() => {
                                    setAddingEhrSchoolId(school.id);
                                    setEhrFormData({ ehr_type_id: '', api_url: '', api_key: '', is_enabled: true, is_default: false });
                                  }}
                                  className="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
                                >
                                  + Add Integration
                                </button>
                              )}
                            </div>

                            {/* Loading state */}
                            {loadingEhrSchoolId === school.id && (
                              <div className="flex items-center justify-center py-4">
                                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500"></div>
                              </div>
                            )}

                            {/* Add new integration form */}
                            {addingEhrSchoolId === school.id && (
                              <div className="mb-4 p-3 bg-slate-800/50 rounded-lg border border-slate-600">
                                <h5 className="text-xs font-medium text-slate-300 mb-3">Add New Integration</h5>
                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                                  <div>
                                    <label className="block text-xs text-slate-400 mb-1">EHR Type</label>
                                    <select
                                      value={ehrFormData.ehr_type_id}
                                      onChange={(e) => {
                                        const selectedEhrTypeId = e.target.value;
                                        const selectedEhrType = ehrTypes.find(t => t.id === selectedEhrTypeId);
                                        setEhrFormData(prev => ({
                                          ...prev,
                                          ehr_type_id: selectedEhrTypeId,
                                          api_url: selectedEhrType?.default_api_url || prev.api_url || ''
                                        }));
                                      }}
                                      className="w-full px-2 py-1.5 bg-slate-700 border border-slate-600 rounded text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    >
                                      <option value="">Select type...</option>
                                      {ehrTypes.map(type => (
                                        <option
                                          key={type.id}
                                          value={type.id}
                                          disabled={getConfiguredEhrTypeIds(school.id).includes(type.id)}
                                        >
                                          {type.ehr_name} {getConfiguredEhrTypeIds(school.id).includes(type.id) ? '(configured)' : ''}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                  <div>
                                    <label className="block text-xs text-slate-400 mb-1">API URL</label>
                                    <input
                                      type="url"
                                      value={ehrFormData.api_url}
                                      onChange={(e) => setEhrFormData(prev => ({ ...prev, api_url: e.target.value }))}
                                      placeholder="https://api.example.com/v1/save"
                                      className="w-full px-2 py-1.5 bg-slate-700 border border-slate-600 rounded text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                  </div>
                                  <div>
                                    <label className="block text-xs text-slate-400 mb-1">API Key (optional)</label>
                                    <input
                                      type="password"
                                      value={ehrFormData.api_key}
                                      onChange={(e) => setEhrFormData(prev => ({ ...prev, api_key: e.target.value }))}
                                      placeholder="Optional API key"
                                      className="w-full px-2 py-1.5 bg-slate-700 border border-slate-600 rounded text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                  </div>
                                  <div className="flex items-center gap-2 pt-5">
                                    <input
                                      type="checkbox"
                                      id="is_default_new"
                                      checked={ehrFormData.is_default}
                                      onChange={(e) => setEhrFormData(prev => ({ ...prev, is_default: e.target.checked }))}
                                      className="h-4 w-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500"
                                    />
                                    <label htmlFor="is_default_new" className="text-xs text-slate-300">
                                      Set as Default
                                    </label>
                                  </div>
                                  <div className="flex items-end gap-2">
                                    <button
                                      onClick={() => handleCreateEhrIntegration(school.id)}
                                      disabled={updatingSchoolId === school.id || !ehrFormData.ehr_type_id}
                                      className="px-3 py-1.5 bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm rounded transition-colors"
                                    >
                                      Save
                                    </button>
                                    <button
                                      onClick={() => {
                                        setAddingEhrSchoolId(null);
                                        setEhrFormData({ ehr_type_id: '', api_url: '', api_key: '', is_enabled: true, is_default: false });
                                      }}
                                      className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded transition-colors"
                                    >
                                      Cancel
                                    </button>
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* Existing integrations list */}
                            {loadingEhrSchoolId !== school.id && (
                              <>
                                {(ehrIntegrations[school.id] || []).length === 0 ? (
                                  <p className="text-sm text-slate-500 italic">No EHR integrations configured</p>
                                ) : (
                                  <div className="space-y-2">
                                    {(ehrIntegrations[school.id] || []).map((integration) => (
                                      <div
                                        key={integration.id}
                                        className={`p-3 rounded-lg border ${
                                          integration.is_enabled
                                            ? 'bg-slate-800/30 border-slate-600'
                                            : 'bg-slate-800/10 border-slate-700 opacity-60'
                                        }`}
                                      >
                                        {editingEhrId === integration.id ? (
                                          // Edit mode
                                          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                                            <div>
                                              <label className="block text-xs text-slate-400 mb-1">EHR Type</label>
                                              <input
                                                type="text"
                                                value={integration.ehr_name || integration.ehr_code?.toUpperCase() || 'UNKNOWN'}
                                                disabled
                                                className="w-full px-2 py-1.5 bg-slate-900 border border-slate-700 rounded text-slate-400 text-sm"
                                              />
                                            </div>
                                            <div>
                                              <label className="block text-xs text-slate-400 mb-1">API URL</label>
                                              <input
                                                type="url"
                                                value={ehrFormData.api_url}
                                                onChange={(e) => setEhrFormData(prev => ({ ...prev, api_url: e.target.value }))}
                                                placeholder="https://api.example.com/v1/save"
                                                className="w-full px-2 py-1.5 bg-slate-700 border border-slate-600 rounded text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                              />
                                            </div>
                                            <div>
                                              <label className="block text-xs text-slate-400 mb-1">
                                                API Key {integration.has_api_key && <span className="text-green-400">(set)</span>}
                                              </label>
                                              <input
                                                type="password"
                                                value={ehrFormData.api_key}
                                                onChange={(e) => setEhrFormData(prev => ({ ...prev, api_key: e.target.value }))}
                                                placeholder={integration.has_api_key ? 'Enter to change, blank to clear' : 'Optional API key'}
                                                className="w-full px-2 py-1.5 bg-slate-700 border border-slate-600 rounded text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                              />
                                            </div>
                                            <div className="flex items-center gap-2 pt-5">
                                              <input
                                                type="checkbox"
                                                id={`is_default_edit_${integration.id}`}
                                                checked={ehrFormData.is_default}
                                                onChange={(e) => setEhrFormData(prev => ({ ...prev, is_default: e.target.checked }))}
                                                className="h-4 w-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500"
                                              />
                                              <label htmlFor={`is_default_edit_${integration.id}`} className="text-xs text-slate-300">
                                                Set as Default
                                              </label>
                                            </div>
                                            <div className="flex items-end gap-2">
                                              <button
                                                onClick={() => handleUpdateEhrIntegration(school.id, integration.id)}
                                                disabled={updatingSchoolId === school.id}
                                                className="px-3 py-1.5 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-sm rounded transition-colors"
                                              >
                                                Save
                                              </button>
                                              <button
                                                onClick={() => {
                                                  setEditingEhrId(null);
                                                  setEhrFormData({ ehr_type_id: '', api_url: '', api_key: '', is_enabled: true, is_default: false });
                                                }}
                                                className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded transition-colors"
                                              >
                                                Cancel
                                              </button>
                                            </div>
                                          </div>
                                        ) : (
                                          // View mode
                                          <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-4">
                                              <span className="px-2 py-1 bg-blue-600/20 text-blue-300 text-xs font-medium rounded">
                                                {integration.ehr_name || integration.ehr_code?.toUpperCase() || 'UNKNOWN'}
                                              </span>
                                              {integration.is_default && (
                                                <span className="px-2 py-0.5 bg-yellow-600/20 text-yellow-400 text-xs font-medium rounded">
                                                  Default
                                                </span>
                                              )}
                                              <span className="text-sm text-slate-300 font-mono">
                                                {integration.api_url || <span className="text-slate-500 italic">No URL configured</span>}
                                              </span>
                                              {integration.has_api_key && (
                                                <span className="px-2 py-0.5 bg-green-600/20 text-green-400 text-xs rounded">
                                                  Key set
                                                </span>
                                              )}
                                            </div>
                                            <div className="flex items-center gap-2">
                                              {/* Set as Default button */}
                                              {!integration.is_default && integration.is_enabled && (
                                                <button
                                                  onClick={() => handleSetDefaultEhr(school.id, integration.id)}
                                                  disabled={updatingSchoolId === school.id}
                                                  className="px-2 py-1 text-xs text-yellow-400 hover:bg-yellow-500/10 rounded transition-colors disabled:opacity-50"
                                                  title="Set as default for new counsellors"
                                                >
                                                  Set Default
                                                </button>
                                              )}
                                              {/* Enable/Disable toggle */}
                                              <button
                                                onClick={() => handleToggleEhrEnabled(school.id, integration)}
                                                disabled={updatingSchoolId === school.id}
                                                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none disabled:opacity-50 ${
                                                  integration.is_enabled ? 'bg-green-600' : 'bg-slate-600'
                                                }`}
                                                title={integration.is_enabled ? 'Enabled' : 'Disabled'}
                                              >
                                                <span
                                                  className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                                                    integration.is_enabled ? 'translate-x-5' : 'translate-x-1'
                                                  }`}
                                                />
                                              </button>
                                              {/* Edit button */}
                                              <button
                                                onClick={() => startEditingEhr(integration)}
                                                className="p-1.5 text-slate-400 hover:text-blue-400 hover:bg-blue-500/10 rounded transition-colors"
                                                title="Edit"
                                              >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                                                </svg>
                                              </button>
                                              {/* Delete button */}
                                              <button
                                                onClick={() => handleDeleteEhrIntegration(school.id, integration.id, integration.ehr_code || '')}
                                                disabled={updatingSchoolId === school.id}
                                                className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
                                                title="Delete"
                                              >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                </svg>
                                              </button>
                                            </div>
                                          </div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </>
                            )}
                          </div>

                          {/* Counsellor EHR Assignment Section */}
                          <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-700">
                            <h4 className="text-sm font-medium text-white mb-4">Counsellor EHR Assignments</h4>
                            <p className="text-xs text-slate-400 mb-4">
                              Assign which EHR system each counsellor&apos;s extractions will be sent to.
                              New counsellors are automatically assigned to the school&apos;s default EHR.
                            </p>

                            {/* Loading state */}
                            {loadingCounsellorsSchoolId === school.id && (
                              <div className="flex items-center justify-center py-4">
                                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500"></div>
                              </div>
                            )}

                            {/* Counsellors list */}
                            {loadingCounsellorsSchoolId !== school.id && (
                              <>
                                {(schoolCounsellors[school.id] || []).length === 0 ? (
                                  <p className="text-sm text-slate-500 italic">No counsellors found for this school</p>
                                ) : (
                                  <div className="space-y-2 max-h-64 overflow-y-auto">
                                    {(schoolCounsellors[school.id] || []).map((counsellor) => (
                                      <div
                                        key={counsellor.id}
                                        className="flex items-center justify-between p-2 bg-slate-800/30 rounded-lg"
                                      >
                                        <span className="text-sm text-slate-200">{counsellor.counsellor_name}</span>
                                        <div className="flex items-center gap-2">
                                          <select
                                            value={counsellor.ehr_type_id || ''}
                                            onChange={(e) => handleUpdateCounsellorEhrType(
                                              school.id,
                                              counsellor.id,
                                              e.target.value || null
                                            )}
                                            disabled={updatingCounsellorId === counsellor.id}
                                            className="px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 min-w-[120px]"
                                          >
                                            <option value="">No EHR</option>
                                            {ehrTypes
                                              .filter(et => getSchoolEhrTypeIds(school.id).includes(et.id))
                                              .map(ehrType => (
                                                <option key={ehrType.id} value={ehrType.id}>
                                                  {ehrType.ehr_name}
                                                </option>
                                              ))}
                                          </select>
                                          {updatingCounsellorId === counsellor.id && (
                                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500"></div>
                                          )}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Info Note */}
      <div className="p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
        <div className="flex items-start gap-3">
          <svg className="w-5 h-5 text-blue-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div className="text-sm text-blue-200">
            <p className="font-medium mb-1">Default Template Priority</p>
            <p className="text-blue-300/80">
              When a counsellor performs an extraction, the template is resolved in this order:
              <span className="font-medium"> Counsellor&apos;s default</span> &rarr;
              <span className="font-medium"> School&apos;s default</span> &rarr;
              <span className="font-medium"> None (manual selection required)</span>
            </p>
          </div>
        </div>
      </div>

      {/* Quality Metrics Modal */}
      {metricsSchool && (
        <QualityMetricsModal
          schoolId={metricsSchool.id}
          schoolName={metricsSchool.school_name}
          onClose={() => setMetricsSchoolId(null)}
        />
      )}
    </div>
  );
}
