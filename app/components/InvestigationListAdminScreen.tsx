'use client';

/**
 * Investigation List Admin Screen
 *
 * Admin interface for managing counsellor investigation lists:
 * 1. Counsellor Investigations - Personal investigation lists with CSV upload
 * 2. School Investigations - Shared school-level investigation lists
 * 3. Feedback Review - Review and process investigation matching feedback
 */

import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '@lib/auth';
import { authGet, authPost, authPut, authDelete, authFetch, API_BASE_URL } from '@lib/apiClient';

// Types
interface Investigation {
  id: string;
  investigation_name: string;
  common_names?: string[];
  investigation_type: string;
  category?: string;
  normal_range?: string;
  loinc_code?: string;
  cpt_code?: string;
  normalized_name?: string;
  external_id?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface Counsellor {
  id: string;
  full_name: string;
  email: string;
  specialization?: string;
}

interface School {
  id: string;
  school_name: string;
}

interface FeedbackRecord {
  id: string;
  original_investigation_name: string;
  matched_investigation_name?: string;
  match_confidence?: number;
  match_method?: string;
  match_source?: string;
  investigation_type?: string;
  feedback_status?: string;
  feedback_at?: string;
  correct_investigation_name?: string;
  created_at: string;
}

type ViewMode = 'doctor-investigations' | 'hospital-investigations' | 'feedback-review';

const INVESTIGATION_TYPES = [
  { value: 'laboratory', label: 'Laboratory Tests' },
  { value: 'imaging', label: 'Imaging Studies' },
  { value: 'other', label: 'Other Investigations' },
];

const INVESTIGATION_CATEGORIES = [
  'Hematology',
  'Biochemistry',
  'Microbiology',
  'Immunology',
  'Endocrinology',
  'Coagulation',
  'Urinalysis',
  'Gastroenterology',
  'Radiology',
  'Cardiology',
  'Neurology',
  'Pulmonology',
  'Nuclear Medicine',
  'Pathology',
  'ENT',
  'Urology',
  'Other',
];

export function InvestigationListAdminScreen() {
  const { getAccessToken } = useAuth();
  const [viewMode, setViewMode] = useState<ViewMode>('doctor-investigations');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Counsellor selection
  const [doctors, setCounsellors] = useState<Counsellor[]>([]);
  const [selectedCounsellorId, setSelectedCounsellorId] = useState<string>('');

  // School selection
  const [hospitals, setSchools] = useState<School[]>([]);
  const [selectedSchoolId, setSelectedSchoolId] = useState<string>('');
  const [hospitalInvestigations, setSchoolInvestigations] = useState<Investigation[]>([]);

  // Data states
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [feedbackRecords, setFeedbackRecords] = useState<FeedbackRecord[]>([]);

  // Modal states
  const [showInvestigationModal, setShowInvestigationModal] = useState(false);
  const [editingInvestigation, setEditingInvestigation] = useState<Investigation | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  // Filter states
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [feedbackFilter, setFeedbackFilter] = useState<string>('pending');
  const [confidenceFilter, setConfidenceFilter] = useState<string>('all');

  // File upload ref
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load counsellors and schools on mount
  useEffect(() => {
    loadCounsellors();
    loadSchools();
  }, []);

  // Load data when counsellor, view mode, or filters change
  useEffect(() => {
    if (selectedCounsellorId) {
      if (viewMode === 'doctor-investigations') {
        loadCounsellorInvestigations();
      } else if (viewMode === 'feedback-review') {
        loadFeedbackRecords();
      }
    }
  }, [selectedCounsellorId, viewMode, feedbackFilter, confidenceFilter, typeFilter]);

  // Load school investigations when school is selected
  useEffect(() => {
    if (selectedSchoolId && viewMode === 'hospital-investigations') {
      loadSchoolInvestigations();
    }
  }, [selectedSchoolId, viewMode, typeFilter, categoryFilter]);

  const loadCounsellors = async () => {
    try {
      const response = await authGet('/api/v1/counsellors', getAccessToken());
      if (!response.ok) throw new Error('Failed to load counsellors');
      const data = await response.json();
      setCounsellors(data.counsellors || []);
      if (data.counsellors?.length > 0 && !selectedCounsellorId) {
        setSelectedCounsellorId(data.counsellors[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load counsellors');
    }
  };

  const loadSchools = async () => {
    try {
      const response = await authGet('/api/v1/counsellors/schools', getAccessToken());
      if (!response.ok) throw new Error('Failed to load schools');
      const data = await response.json();
      setSchools(data.schools || []);
      if (data.schools?.length > 0 && !selectedSchoolId) {
        setSelectedSchoolId(data.schools[0].id);
      }
    } catch (err) {
      // Silently fail - schools endpoint might not exist yet
      console.error('Failed to load schools:', err);
    }
  };

  const loadSchoolInvestigations = async () => {
    if (!selectedSchoolId) return;
    try {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams();
      if (typeFilter !== 'all') params.append('investigation_type', typeFilter);
      if (categoryFilter !== 'all') params.append('category', categoryFilter);

      const response = await authGet(
        `/api/v1/investigations/school/${selectedSchoolId}?${params.toString()}`,
        getAccessToken()
      );
      if (!response.ok) throw new Error('Failed to load school investigations');
      const data = await response.json();
      setSchoolInvestigations(data.investigations || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load school investigations');
    } finally {
      setLoading(false);
    }
  };

  const loadCounsellorInvestigations = async () => {
    if (!selectedCounsellorId) return;
    try {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams();
      if (typeFilter !== 'all') params.append('investigation_type', typeFilter);
      if (categoryFilter !== 'all') params.append('category', categoryFilter);
      if (searchQuery) params.append('search', searchQuery);

      const response = await authGet(
        `/api/v1/investigations/${selectedCounsellorId}?${params.toString()}`,
        getAccessToken()
      );
      if (!response.ok) throw new Error('Failed to load investigations');
      const data = await response.json();
      setInvestigations(data.investigations || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load investigations');
    } finally {
      setLoading(false);
    }
  };

  const loadFeedbackRecords = async () => {
    if (!selectedCounsellorId) return;
    try {
      setLoading(true);
      setError(null);

      const endpoint = feedbackFilter === 'pending'
        ? `/api/v1/investigations/feedback/${selectedCounsellorId}/pending`
        : `/api/v1/investigations/feedback/${selectedCounsellorId}/history`;

      const params = new URLSearchParams();
      if (feedbackFilter !== 'pending' && feedbackFilter !== 'all') {
        params.append('feedback_status', feedbackFilter);
      }
      if (typeFilter !== 'all') {
        params.append('investigation_type', typeFilter);
      }
      if (confidenceFilter !== 'all') {
        const [min, max] = confidenceFilter.split('-').map(Number);
        if (!isNaN(min)) params.append('confidence_min', String(min / 100));
        if (!isNaN(max)) params.append('confidence_max', String(max / 100));
      }
      if (searchQuery) params.append('search', searchQuery);

      const response = await authGet(`${endpoint}?${params.toString()}`, getAccessToken());
      if (!response.ok) throw new Error('Failed to load feedback records');
      const data = await response.json();
      setFeedbackRecords(data.records || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load feedback');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteInvestigation = async (investigationId: string) => {
    if (!confirm('Are you sure you want to delete this investigation?')) return;

    try {
      const response = await authDelete(
        `/api/v1/investigations/${selectedCounsellorId}/${investigationId}`,
        getAccessToken()
      );
      if (!response.ok) throw new Error('Failed to delete investigation');
      setSuccessMessage('Investigation deleted successfully');
      loadCounsellorInvestigations();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete');
    }
  };

  const handleFileUpload = async (file: File, replaceExisting: boolean) => {
    try {
      setIsUploading(true);
      setError(null);

      const formData = new FormData();
      formData.append('file', file);

      const response = await authFetch(
        `${API_BASE_URL}/api/v1/investigations/${selectedCounsellorId}/upload?replace_existing=${replaceExisting}`,
        getAccessToken(),
        {
          method: 'POST',
          body: formData,
        }
      );

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.detail || 'Failed to upload file');
      }
      const result = await response.json();
      setSuccessMessage(
        `Upload complete: ${result.successful || result.successful_imports || 0} imported, ${result.failed || result.failed_imports || 0} failed`
      );
      setShowUploadModal(false);
      loadCounsellorInvestigations();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload');
    } finally {
      setIsUploading(false);
    }
  };

  const handleSubmitFeedback = async (recordId: string, status: 'agreed' | 'disagreed', correctInvestigationName?: string) => {
    try {
      const response = await authPost(
        `/api/v1/investigations/feedback/${recordId}`,
        getAccessToken(),
        {
          feedback_status: status,
          correct_investigation_name: correctInvestigationName,
        }
      );
      if (!response.ok) throw new Error('Failed to submit feedback');
      setSuccessMessage('Feedback submitted successfully');
      loadFeedbackRecords();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit feedback');
    }
  };

  const handleBulkAgree = async () => {
    const pendingIds = feedbackRecords.filter(r => !r.feedback_status).map(r => r.id);
    if (pendingIds.length === 0) return;

    if (!confirm(`Agree with ${pendingIds.length} matches?`)) return;

    try {
      setLoading(true);
      const response = await authPost(
        `/api/v1/investigations/feedback/bulk-agree?counsellor_id=${selectedCounsellorId}`,
        getAccessToken(),
        pendingIds
      );
      if (!response.ok) throw new Error('Failed to bulk agree');
      const result = await response.json();
      setSuccessMessage(`Bulk agree: ${result.success_count} successful, ${result.error_count} errors`);
      loadFeedbackRecords();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to bulk agree');
    } finally {
      setLoading(false);
    }
  };

  // Clear messages after 5 seconds
  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [successMessage]);

  const filteredInvestigations = investigations.filter(inv => {
    if (searchQuery.trim()) {
      const search = searchQuery.toLowerCase();
      return (
        inv.investigation_name.toLowerCase().includes(search) ||
        inv.common_names?.some(n => n.toLowerCase().includes(search)) ||
        inv.category?.toLowerCase().includes(search)
      );
    }
    return true;
  });

  const filteredSchoolInvestigations = hospitalInvestigations.filter(inv => {
    if (searchQuery.trim()) {
      const search = searchQuery.toLowerCase();
      return (
        inv.investigation_name.toLowerCase().includes(search) ||
        inv.common_names?.some(n => n.toLowerCase().includes(search)) ||
        inv.category?.toLowerCase().includes(search)
      );
    }
    return true;
  });

  const handleDeleteSchoolInvestigation = async (investigationId: string) => {
    if (!confirm('Are you sure you want to delete this hospital investigation?')) return;

    try {
      const response = await authDelete(
        `/api/v1/investigations/school/${selectedSchoolId}/${investigationId}`,
        getAccessToken()
      );
      if (!response.ok) throw new Error('Failed to delete school investigation');
      setSuccessMessage('School investigation deleted successfully');
      loadSchoolInvestigations();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete');
    }
  };

  const handleSchoolFileUpload = async (file: File, replaceExisting: boolean) => {
    if (!selectedSchoolId || !selectedCounsellorId) {
      setError('Please select both a school and a counsellor (as admin)');
      return;
    }

    try {
      setIsUploading(true);
      setError(null);

      const formData = new FormData();
      formData.append('file', file);

      const response = await authFetch(
        `${API_BASE_URL}/api/v1/investigations/school/${selectedSchoolId}/upload?created_by=${selectedCounsellorId}&replace_existing=${replaceExisting}`,
        getAccessToken(),
        {
          method: 'POST',
          body: formData,
        }
      );

      if (!response.ok) throw new Error('Failed to upload file');
      const result = await response.json();
      setSuccessMessage(
        `Upload complete: ${result.successful_imports || 0} imported, ${result.failed_imports || 0} failed`
      );
      setShowUploadModal(false);
      loadSchoolInvestigations();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload');
    } finally {
      setIsUploading(false);
    }
  };

  const getInvestigationTypeBadge = (type: string) => {
    switch (type) {
      case 'laboratory':
        return 'bg-blue-100 text-blue-700';
      case 'imaging':
        return 'bg-purple-100 text-purple-700';
      case 'other':
        return 'bg-gray-100 text-gray-700';
      default:
        return 'bg-gray-100 text-gray-700';
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Investigation List Management</h1>
            <p className="text-sm text-gray-600 mt-1">
              {viewMode === 'doctor-investigations'
                ? 'Manage personal investigation lists for counsellors'
                : viewMode === 'hospital-investigations'
                ? 'Manage school-wide shared investigation lists'
                : 'Review and process investigation matching feedback'}
            </p>
          </div>
          {viewMode === 'doctor-investigations' && selectedCounsellorId && (
            <div className="flex gap-2">
              <button
                onClick={() => setShowUploadModal(true)}
                className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
              >
                Upload CSV
              </button>
              <button
                onClick={() => {
                  setEditingInvestigation(null);
                  setShowInvestigationModal(true);
                }}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
              >
                + Add Investigation
              </button>
            </div>
          )}
          {viewMode === 'hospital-investigations' && selectedSchoolId && (
            <div className="flex gap-2">
              <button
                onClick={() => setShowUploadModal(true)}
                className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
              >
                Upload CSV
              </button>
              <button
                onClick={() => {
                  setEditingInvestigation(null);
                  setShowInvestigationModal(true);
                }}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
              >
                + Add Investigation
              </button>
            </div>
          )}
          {viewMode === 'feedback-review' && feedbackRecords.some(r => !r.feedback_status) && (
            <button
              onClick={handleBulkAgree}
              className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
            >
              Bulk Agree ({feedbackRecords.filter(r => !r.feedback_status).length})
            </button>
          )}
        </div>
      </div>

      {/* View Mode Tabs */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <div className="flex gap-2">
          <button
            onClick={() => setViewMode('doctor-investigations')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'doctor-investigations'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Counsellor Investigations
          </button>
          <button
            onClick={() => setViewMode('hospital-investigations')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'hospital-investigations'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            School Investigations
          </button>
          <button
            onClick={() => setViewMode('feedback-review')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'feedback-review'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Feedback Review
          </button>
        </div>
      </div>

      {/* Counsellor Selector */}
      {(viewMode === 'doctor-investigations' || viewMode === 'feedback-review') && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Select Counsellor
          </label>
          <select
            value={selectedCounsellorId}
            onChange={(e) => setSelectedCounsellorId(e.target.value)}
            className="w-full max-w-md px-3 py-2 border border-gray-300 rounded-lg bg-white"
            style={{ color: '#111827' }}
          >
            <option value="" style={{ color: '#111827' }}>-- Select a Counsellor --</option>
            {doctors.map(doctor => (
              <option key={doctor.id} value={doctor.id} style={{ color: '#111827' }}>
                {doctor.full_name} {doctor.specialization ? `(${doctor.specialization})` : ''}
              </option>
            ))}
          </select>
          {doctors.length === 0 && (
            <p className="text-sm text-amber-600 mt-2">
              No counsellors found. Make sure the backend is running and counsellors exist in the database.
            </p>
          )}
        </div>
      )}

      {/* Messages */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">{error}</p>
        </div>
      )}
      {successMessage && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <p className="text-green-800">{successMessage}</p>
        </div>
      )}

      {/* Counsellor Investigations View */}
      {viewMode === 'doctor-investigations' && selectedCounsellorId && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-200">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">
                Investigation List ({filteredInvestigations.length} of {investigations.length})
              </h2>
              <div className="flex gap-2">
                <select
                  value={typeFilter}
                  onChange={(e) => {
                    setTypeFilter(e.target.value);
                  }}
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
                >
                  <option value="all">All Types</option>
                  {INVESTIGATION_TYPES.map(type => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
                <select
                  value={categoryFilter}
                  onChange={(e) => {
                    setCategoryFilter(e.target.value);
                    loadCounsellorInvestigations();
                  }}
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
                >
                  <option value="all">All Categories</option>
                  {INVESTIGATION_CATEGORIES.map(cat => (
                    <option key={cat} value={cat}>{cat}</option>
                  ))}
                </select>
              </div>
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search investigations..."
              className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
            />
          </div>

          {loading ? (
            <div className="p-8 text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Loading investigations...</p>
            </div>
          ) : filteredInvestigations.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <p>No investigations found</p>
              <button
                onClick={() => setShowUploadModal(true)}
                className="text-blue-600 hover:text-blue-700 font-medium mt-2"
              >
                Upload a CSV to get started
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Investigation Name
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Type
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Category
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Common Names
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {filteredInvestigations.map(investigation => (
                    <tr key={investigation.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="font-medium text-gray-900">{investigation.investigation_name}</div>
                          {investigation.external_id && (
                            <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                              #{investigation.external_id}
                            </span>
                          )}
                        </div>
                        {investigation.normal_range && (
                          <div className="text-xs text-gray-500">Range: {investigation.normal_range}</div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-xs px-2 py-1 rounded ${getInvestigationTypeBadge(investigation.investigation_type)}`}>
                          {investigation.investigation_type}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {investigation.category || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {investigation.common_names?.join(', ') || '-'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          <button
                            onClick={() => {
                              setEditingInvestigation(investigation);
                              setShowInvestigationModal(true);
                            }}
                            className="text-blue-600 hover:text-blue-700 text-sm font-medium"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDeleteInvestigation(investigation.id)}
                            className="text-red-600 hover:text-red-700 text-sm font-medium"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Feedback Review View */}
      {viewMode === 'feedback-review' && selectedCounsellorId && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-200">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">
                Feedback Review ({feedbackRecords.length})
              </h2>
              <div className="flex gap-2">
                <select
                  value={feedbackFilter}
                  onChange={(e) => {
                    setFeedbackFilter(e.target.value);
                  }}
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
                >
                  <option value="pending">Pending</option>
                  <option value="agreed">Agreed</option>
                  <option value="disagreed">Disagreed</option>
                  <option value="all">All</option>
                </select>
                <select
                  value={typeFilter}
                  onChange={(e) => {
                    setTypeFilter(e.target.value);
                  }}
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
                >
                  <option value="all">All Types</option>
                  {INVESTIGATION_TYPES.map(type => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
                <select
                  value={confidenceFilter}
                  onChange={(e) => {
                    setConfidenceFilter(e.target.value);
                  }}
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
                >
                  <option value="all">All Confidence</option>
                  <option value="0-50">Low (0-50%)</option>
                  <option value="50-80">Medium (50-80%)</option>
                  <option value="80-100">High (80-100%)</option>
                </select>
              </div>
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by investigation name..."
              className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
            />
          </div>

          {loading ? (
            <div className="p-8 text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Loading feedback...</p>
            </div>
          ) : feedbackRecords.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <p>No feedback records found</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {feedbackRecords.map(record => (
                <FeedbackRecordRow
                  key={record.id}
                  record={record}
                  investigations={investigations}
                  onSubmitFeedback={handleSubmitFeedback}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* School Selector */}
      {viewMode === 'hospital-investigations' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Select School
          </label>
          <select
            value={selectedSchoolId}
            onChange={(e) => setSelectedSchoolId(e.target.value)}
            className="w-full max-w-md px-3 py-2 border border-gray-300 rounded-lg bg-white"
            style={{ color: '#111827' }}
          >
            <option value="" style={{ color: '#111827' }}>-- Select a School --</option>
            {hospitals.map(hospital => (
              <option key={hospital.id} value={hospital.id} style={{ color: '#111827' }}>
                {hospital.school_name}
              </option>
            ))}
          </select>
          {hospitals.length === 0 && (
            <p className="text-sm text-amber-600 mt-2">
              No schools found. Make sure the backend is running and schools exist in the database.
            </p>
          )}
        </div>
      )}

      {/* School Investigations View */}
      {viewMode === 'hospital-investigations' && selectedSchoolId && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-200">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">
                School Investigation List ({hospitalInvestigations.length})
              </h2>
              <div className="flex gap-2">
                <select
                  value={typeFilter}
                  onChange={(e) => {
                    setTypeFilter(e.target.value);
                  }}
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
                >
                  <option value="all">All Types</option>
                  {INVESTIGATION_TYPES.map(type => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
                <select
                  value={categoryFilter}
                  onChange={(e) => {
                    setCategoryFilter(e.target.value);
                  }}
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
                >
                  <option value="all">All Categories</option>
                  {INVESTIGATION_CATEGORIES.map(cat => (
                    <option key={cat} value={cat}>{cat}</option>
                  ))}
                </select>
              </div>
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search investigations..."
              className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
            />
          </div>

          {loading ? (
            <div className="p-8 text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Loading school investigations...</p>
            </div>
          ) : filteredSchoolInvestigations.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <p>No school investigations found</p>
              <button
                onClick={() => setShowUploadModal(true)}
                className="text-blue-600 hover:text-blue-700 font-medium mt-2"
              >
                Upload a CSV to get started
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Investigation Name
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Type
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Category
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Common Names
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {filteredSchoolInvestigations.map(investigation => (
                    <tr key={investigation.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="font-medium text-gray-900">{investigation.investigation_name}</div>
                          {investigation.external_id && (
                            <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                              #{investigation.external_id}
                            </span>
                          )}
                        </div>
                        {investigation.normal_range && (
                          <div className="text-xs text-gray-500">Range: {investigation.normal_range}</div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-xs px-2 py-1 rounded ${getInvestigationTypeBadge(investigation.investigation_type)}`}>
                          {investigation.investigation_type}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {investigation.category || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {investigation.common_names?.join(', ') || '-'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          <button
                            onClick={() => {
                              setEditingInvestigation(investigation);
                              setShowInvestigationModal(true);
                            }}
                            className="text-blue-600 hover:text-blue-700 text-sm font-medium"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDeleteSchoolInvestigation(investigation.id)}
                            className="text-red-600 hover:text-red-700 text-sm font-medium"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Investigation Modal */}
      {showInvestigationModal && (
        <InvestigationModal
          investigation={editingInvestigation}
          onClose={() => {
            setShowInvestigationModal(false);
            setEditingInvestigation(null);
          }}
          onSave={async (data) => {
            try {
              // Determine if we're in school or counsellor context
              const isSchoolContext = viewMode === 'hospital-investigations';

              if (isSchoolContext) {
                // School investigation save
                if (!selectedSchoolId) {
                  setError('Please select a school first');
                  return;
                }
                if (!selectedCounsellorId) {
                  setError('Please select a counsellor as admin for audit trail');
                  return;
                }

                const endpoint = editingInvestigation
                  ? `/api/v1/investigations/school/${selectedSchoolId}/${editingInvestigation.id}`
                  : `/api/v1/investigations/school/${selectedSchoolId}?created_by=${selectedCounsellorId}`;

                const response = editingInvestigation
                  ? await authPut(endpoint, getAccessToken(), data)
                  : await authPost(endpoint, getAccessToken(), data);

                if (!response.ok) throw new Error('Failed to save school investigation');
                setSuccessMessage(editingInvestigation ? 'School investigation updated' : 'School investigation added');
                setShowInvestigationModal(false);
                setEditingInvestigation(null);
                loadSchoolInvestigations();
              } else {
                // Counsellor investigation save
                const endpoint = editingInvestigation
                  ? `/api/v1/investigations/${selectedCounsellorId}/${editingInvestigation.id}`
                  : `/api/v1/investigations/${selectedCounsellorId}`;

                const response = editingInvestigation
                  ? await authPut(endpoint, getAccessToken(), data)
                  : await authPost(endpoint, getAccessToken(), data);

                if (!response.ok) throw new Error('Failed to save investigation');
                setSuccessMessage(editingInvestigation ? 'Investigation updated' : 'Investigation added');
                setShowInvestigationModal(false);
                setEditingInvestigation(null);
                loadCounsellorInvestigations();
              }
            } catch (err) {
              setError(err instanceof Error ? err.message : 'Failed to save');
            }
          }}
        />
      )}

      {/* Upload Modal */}
      {showUploadModal && (
        <UploadModal
          onClose={() => { setShowUploadModal(false); setError(null); }}
          onUpload={viewMode === 'hospital-investigations' ? handleSchoolFileUpload : handleFileUpload}
          fileInputRef={fileInputRef}
          isSchoolUpload={viewMode === 'hospital-investigations'}
          isUploading={isUploading}
          uploadError={error}
        />
      )}
    </div>
  );
}

// Feedback Record Row Component
interface FeedbackRecordRowProps {
  record: FeedbackRecord;
  investigations: Investigation[];
  onSubmitFeedback: (id: string, status: 'agreed' | 'disagreed', correctInvestigationName?: string) => void;
}

function FeedbackRecordRow({ record, investigations, onSubmitFeedback }: FeedbackRecordRowProps) {
  const [showCorrection, setShowCorrection] = useState(false);
  const [correctName, setCorrectName] = useState('');

  const confidenceColor = (confidence?: number) => {
    if (!confidence) return 'bg-gray-100 text-gray-700';
    if (confidence >= 0.8) return 'bg-green-100 text-green-700';
    if (confidence >= 0.5) return 'bg-yellow-100 text-yellow-700';
    return 'bg-red-100 text-red-700';
  };

  const getTypeBadge = (type?: string) => {
    switch (type) {
      case 'laboratory':
        return 'bg-blue-100 text-blue-700';
      case 'imaging':
        return 'bg-purple-100 text-purple-700';
      case 'other':
        return 'bg-gray-100 text-gray-700';
      default:
        return 'bg-gray-100 text-gray-700';
    }
  };

  return (
    <div className="p-4 hover:bg-gray-50">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium text-gray-900">{record.original_investigation_name}</span>
            <span className="text-gray-400">→</span>
            <span className={`font-medium ${record.matched_investigation_name ? 'text-blue-600' : 'text-red-600'}`}>
              {record.matched_investigation_name || 'No Match'}
            </span>
          </div>
          <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
            {record.investigation_type && (
              <span className={`px-2 py-0.5 rounded ${getTypeBadge(record.investigation_type)}`}>
                {record.investigation_type}
              </span>
            )}
            {record.match_confidence !== undefined && (
              <span className={`px-2 py-0.5 rounded ${confidenceColor(record.match_confidence)}`}>
                {(record.match_confidence * 100).toFixed(0)}% confidence
              </span>
            )}
            {record.match_method && (
              <span className="bg-gray-100 text-gray-700 px-2 py-0.5 rounded">
                {record.match_method}
              </span>
            )}
            {record.match_source && (
              <span className="bg-purple-100 text-purple-700 px-2 py-0.5 rounded">
                {record.match_source}
              </span>
            )}
          </div>
          {record.feedback_status && (
            <div className="mt-2">
              <span className={`text-xs px-2 py-0.5 rounded ${
                record.feedback_status === 'agreed' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
              }`}>
                {record.feedback_status.toUpperCase()}
                {record.correct_investigation_name && ` → ${record.correct_investigation_name}`}
              </span>
            </div>
          )}
        </div>

        {!record.feedback_status && (
          <div className="flex items-center gap-2 ml-4">
            {showCorrection ? (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={correctName}
                  onChange={(e) => setCorrectName(e.target.value)}
                  placeholder="Correct investigation name"
                  className="px-2 py-1 border border-gray-300 rounded text-sm w-48"
                  list="investigation-suggestions"
                />
                <datalist id="investigation-suggestions">
                  {investigations.map(inv => (
                    <option key={inv.id} value={inv.investigation_name} />
                  ))}
                </datalist>
                <button
                  onClick={() => {
                    if (correctName) {
                      onSubmitFeedback(record.id, 'disagreed', correctName);
                    }
                    setShowCorrection(false);
                    setCorrectName('');
                  }}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-2 py-1 rounded text-sm"
                >
                  Submit
                </button>
                <button
                  onClick={() => {
                    setShowCorrection(false);
                    setCorrectName('');
                  }}
                  className="text-gray-500 hover:text-gray-700 text-sm"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <>
                <button
                  onClick={() => onSubmitFeedback(record.id, 'agreed')}
                  className="bg-green-600 hover:bg-green-700 text-white px-3 py-1.5 rounded text-sm font-medium"
                >
                  Agree
                </button>
                <button
                  onClick={() => setShowCorrection(true)}
                  className="bg-red-600 hover:bg-red-700 text-white px-3 py-1.5 rounded text-sm font-medium"
                >
                  Disagree
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Investigation Modal Component
interface InvestigationModalProps {
  investigation: Investigation | null;
  onClose: () => void;
  onSave: (data: Partial<Investigation>) => void;
}

function InvestigationModal({ investigation, onClose, onSave }: InvestigationModalProps) {
  const [formData, setFormData] = useState({
    investigation_name: investigation?.investigation_name || '',
    common_names: investigation?.common_names?.join(', ') || '',
    investigation_type: investigation?.investigation_type || 'laboratory',
    category: investigation?.category || '',
    normal_range: investigation?.normal_range || '',
    loinc_code: investigation?.loinc_code || '',
    cpt_code: investigation?.cpt_code || '',
  });

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-200">
          <h2 className="text-xl font-bold text-gray-900">
            {investigation ? 'Edit Investigation' : 'Add Investigation'}
          </h2>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Investigation Name *
            </label>
            <input
              type="text"
              value={formData.investigation_name}
              onChange={(e) => setFormData({ ...formData, investigation_name: e.target.value })}
              placeholder="e.g., Complete Blood Count"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Investigation Type *
              </label>
              <select
                value={formData.investigation_type}
                onChange={(e) => setFormData({ ...formData, investigation_type: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
              >
                {INVESTIGATION_TYPES.map(type => (
                  <option key={type.value} value={type.value}>{type.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Category
              </label>
              <select
                value={formData.category}
                onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
              >
                <option value="">Select category</option>
                {INVESTIGATION_CATEGORIES.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Common Names (comma-separated)
            </label>
            <input
              type="text"
              value={formData.common_names}
              onChange={(e) => setFormData({ ...formData, common_names: e.target.value })}
              placeholder="e.g., CBC, hemogram, blood count"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
            />
            <p className="text-xs text-gray-500 mt-1">
              Alternative names or abbreviations the counsellor commonly uses
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Normal Range
            </label>
            <input
              type="text"
              value={formData.normal_range}
              onChange={(e) => setFormData({ ...formData, normal_range: e.target.value })}
              placeholder="e.g., WBC: 4.5-11.0 x10^9/L, RBC: 4.5-5.5 x10^12/L"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                LOINC Code
              </label>
              <input
                type="text"
                value={formData.loinc_code}
                onChange={(e) => setFormData({ ...formData, loinc_code: e.target.value })}
                placeholder="For lab tests (optional)"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                CPT Code
              </label>
              <input
                type="text"
                value={formData.cpt_code}
                onChange={(e) => setFormData({ ...formData, cpt_code: e.target.value })}
                placeholder="For procedures (optional)"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
              />
            </div>
          </div>
        </div>

        <div className="p-6 border-t border-gray-200 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave({
              ...formData,
              common_names: formData.common_names
                ? formData.common_names.split(',').map(n => n.trim()).filter(Boolean)
                : [],
            })}
            disabled={!formData.investigation_name || !formData.investigation_type}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {investigation ? 'Update' : 'Add'}
          </button>
        </div>
      </div>
    </div>
  );
}

// Upload Modal Component
interface UploadModalProps {
  onClose: () => void;
  onUpload: (file: File, replaceExisting: boolean) => void;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  isSchoolUpload?: boolean;
  isUploading?: boolean;
  uploadError?: string | null;
}

function UploadModal({ onClose, onUpload, fileInputRef, isSchoolUpload = false, isUploading = false, uploadError = null }: UploadModalProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [replaceExisting, setReplaceExisting] = useState(false);

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-lg w-full">
        <div className="p-6 border-b border-gray-200">
          <h2 className="text-xl font-bold text-gray-900">
            {isSchoolUpload ? 'Upload School Investigation List' : 'Upload Investigation List'}
          </h2>
          {isSchoolUpload && (
            <p className="text-sm text-gray-600 mt-1">
              School investigations are shared across all counsellors in this school.
            </p>
          )}
        </div>

        <div className="p-6 space-y-4">
          {isUploading ? (
            /* Processing State */
            <div className="border-2 border-blue-200 bg-blue-50 rounded-lg p-8 text-center">
              <div className="flex flex-col items-center gap-4">
                <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-500 border-t-transparent"></div>
                <div>
                  <p className="font-medium text-blue-900">Processing...</p>
                  <p className="text-sm text-blue-700 mt-1">
                    Uploading and importing investigations from CSV
                  </p>
                  {selectedFile && (
                    <p className="text-xs text-blue-600 mt-2">
                      {selectedFile.name}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ) : (
            /* File Selection State */
            <div
              className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center cursor-pointer hover:border-blue-500 transition-colors"
              onClick={() => fileInputRef.current?.click()}
            >
              {selectedFile ? (
                <div>
                  <p className="font-medium text-gray-900">{selectedFile.name}</p>
                  <p className="text-sm text-gray-500 mt-1">
                    {(selectedFile.size / 1024).toFixed(1)} KB
                  </p>
                </div>
              ) : (
                <div>
                  <p className="text-gray-600">Click to select a CSV file</p>
                  <p className="text-sm text-gray-400 mt-1">or drag and drop</p>
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) setSelectedFile(file);
                }}
              />
            </div>
          )}

          <div className="bg-gray-50 rounded-lg p-4">
            <h4 className="font-medium text-gray-900 mb-2">Supported CSV Formats</h4>
            <div className="space-y-2">
              <div>
                <p className="text-xs text-gray-700 font-medium">Standard Format:</p>
                <p className="text-xs text-gray-600 font-mono">
                  name, common_names, type, category, normal_range, loinc_code, cpt_code
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-700 font-medium">Alternate Format (auto-mapped):</p>
                <p className="text-xs text-gray-600 font-mono">
                  testID, TestName, test_ShortName, Type
                </p>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Column headers are case-insensitive. Type values like &quot;LAB&quot; are auto-mapped to &quot;laboratory&quot;.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="replace_existing"
              checked={replaceExisting}
              onChange={(e) => setReplaceExisting(e.target.checked)}
              disabled={isUploading}
              className="w-4 h-4 text-blue-600 border-gray-300 rounded disabled:opacity-50"
            />
            <label htmlFor="replace_existing" className={`text-sm ${isUploading ? 'text-gray-400' : 'text-gray-700'}`}>
              {isSchoolUpload
                ? 'Replace all existing school investigations (instead of merging)'
                : 'Replace all existing investigations (instead of merging)'}
            </label>
          </div>
        </div>

        {uploadError && (
          <div className="px-6 pb-2">
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-sm text-red-800">{uploadError}</p>
            </div>
          </div>
        )}

        <div className="p-6 border-t border-gray-200 flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={isUploading}
            className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              if (selectedFile && !isUploading) {
                onUpload(selectedFile, replaceExisting);
              }
            }}
            disabled={!selectedFile || isUploading}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isUploading ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                Uploading...
              </>
            ) : (
              'Upload'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
