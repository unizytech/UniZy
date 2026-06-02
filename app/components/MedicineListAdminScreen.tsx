'use client';

/**
 * Medicine List Admin Screen
 *
 * Admin interface for managing counsellor medicine lists:
 * 1. Counsellor Medicines - Personal medicine lists with CSV upload
 * 2. School Medicines - Shared school-level medicine lists
 * 3. Feedback Review - Review and process medicine matching feedback
 */

import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '@lib/auth';
import { authGet, authPost, authPut, authDelete, authFetch, API_BASE_URL } from '@lib/apiClient';

// Types
interface Medicine {
  id: string;
  medicine_name: string;
  common_names?: string[];
  category?: string;
  typical_dosage?: string;
  form?: string;
  snomed_code?: string;
  formulary_name?: string;
  medicine_type?: string;
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
  original_medicine_name: string;
  matched_medicine_name?: string;
  match_confidence?: number;
  match_method?: string;
  match_source?: string;
  diagnosis_context?: string;
  feedback_status?: string;
  feedback_at?: string;
  correct_medicine_name?: string;
  created_at: string;
}

type ViewMode = 'counsellor-medicines' | 'school-medicines' | 'feedback-review';

const MEDICINE_CATEGORIES = [
  'Antihypertensive',
  'Antibiotic',
  'Analgesic',
  'Antidiabetic',
  'Antihistamine',
  'Antacid',
  'Bronchodilator',
  'Cardiac',
  'Dermatological',
  'Gastrointestinal',
  'Neurological',
  'Ophthalmic',
  'Psychiatric',
  'Respiratory',
  'Vitamin/Supplement',
  'Other',
];

const MEDICINE_FORMS = [
  'Tablet',
  'Capsule',
  'Syrup',
  'Injection',
  'Drops',
  'Cream',
  'Ointment',
  'Inhaler',
  'Patch',
  'Suppository',
  'Powder',
  'Vaccine',
  'Penfill',
  'Spray',
  'Oil',
  'Soap',
  'Other',
];

export function MedicineListAdminScreen() {
  const { getAccessToken } = useAuth();
  const [viewMode, setViewMode] = useState<ViewMode>('counsellor-medicines');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Counsellor selection
  const [counsellors, setCounsellors] = useState<Counsellor[]>([]);
  const [selectedCounsellorId, setSelectedCounsellorId] = useState<string>('');

  // School selection
  const [schools, setSchools] = useState<School[]>([]);
  const [selectedSchoolId, setSelectedSchoolId] = useState<string>('');
  const [schoolMedicines, setSchoolMedicines] = useState<Medicine[]>([]);

  // Data states
  const [medicines, setMedicines] = useState<Medicine[]>([]);
  const [feedbackRecords, setFeedbackRecords] = useState<FeedbackRecord[]>([]);

  // Modal states
  const [showMedicineModal, setShowMedicineModal] = useState(false);
  const [editingMedicine, setEditingMedicine] = useState<Medicine | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  // Filter states
  const [searchQuery, setSearchQuery] = useState('');
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
      if (viewMode === 'counsellor-medicines') {
        loadCounsellorMedicines();
      } else if (viewMode === 'feedback-review') {
        loadFeedbackRecords();
      }
    }
  }, [selectedCounsellorId, viewMode, feedbackFilter, confidenceFilter]);

  // Load school medicines when school is selected
  useEffect(() => {
    if (selectedSchoolId && viewMode === 'school-medicines') {
      loadSchoolMedicines();
    }
  }, [selectedSchoolId, viewMode]);

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

  const loadSchoolMedicines = async () => {
    if (!selectedSchoolId) return;
    try {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams();
      if (categoryFilter !== 'all') params.append('category', categoryFilter);

      const response = await authGet(
        `/api/v1/medicines/school/${selectedSchoolId}?${params.toString()}`,
        getAccessToken()
      );
      if (!response.ok) throw new Error('Failed to load school medicines');
      const data = await response.json();
      setSchoolMedicines(data.medicines || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load school medicines');
    } finally {
      setLoading(false);
    }
  };

  const loadCounsellorMedicines = async () => {
    if (!selectedCounsellorId) return;
    try {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams();
      if (categoryFilter !== 'all') params.append('category', categoryFilter);
      if (searchQuery) params.append('search', searchQuery);

      const response = await authGet(
        `/api/v1/medicines/${selectedCounsellorId}?${params.toString()}`,
        getAccessToken()
      );
      if (!response.ok) throw new Error('Failed to load medicines');
      const data = await response.json();
      setMedicines(data.medicines || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load medicines');
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
        ? `/api/v1/medicines/feedback/${selectedCounsellorId}/pending`
        : `/api/v1/medicines/feedback/${selectedCounsellorId}/history`;

      const params = new URLSearchParams();
      if (feedbackFilter !== 'pending' && feedbackFilter !== 'all') {
        params.append('feedback_status', feedbackFilter);
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

  const handleDeleteMedicine = async (medicineId: string) => {
    if (!confirm('Are you sure you want to delete this medicine?')) return;

    try {
      const response = await authDelete(
        `/api/v1/medicines/${selectedCounsellorId}/${medicineId}`,
        getAccessToken()
      );
      if (!response.ok) throw new Error('Failed to delete medicine');
      setSuccessMessage('Medicine deleted successfully');
      loadCounsellorMedicines();
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
        `${API_BASE_URL}/api/v1/medicines/${selectedCounsellorId}/upload?replace_existing=${replaceExisting}`,
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
      loadCounsellorMedicines();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload');
    } finally {
      setIsUploading(false);
    }
  };

  const handleSubmitFeedback = async (recordId: string, status: 'agreed' | 'disagreed', correctMedicineName?: string) => {
    try {
      const response = await authPost(
        `/api/v1/medicines/feedback/${recordId}?counsellor_id=${selectedCounsellorId}`,
        getAccessToken(),
        {
          feedback_status: status,
          correct_medicine_name: correctMedicineName,
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
        `/api/v1/medicines/feedback/bulk-agree?counsellor_id=${selectedCounsellorId}`,
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

  const filteredMedicines = medicines.filter(med => {
    if (searchQuery.trim()) {
      const search = searchQuery.toLowerCase();
      return (
        med.medicine_name.toLowerCase().includes(search) ||
        med.common_names?.some(n => n.toLowerCase().includes(search)) ||
        med.category?.toLowerCase().includes(search)
      );
    }
    return true;
  });

  const filteredSchoolMedicines = schoolMedicines.filter(med => {
    if (searchQuery.trim()) {
      const search = searchQuery.toLowerCase();
      return (
        med.medicine_name.toLowerCase().includes(search) ||
        med.common_names?.some(n => n.toLowerCase().includes(search)) ||
        med.category?.toLowerCase().includes(search)
      );
    }
    return true;
  });

  const handleDeleteSchoolMedicine = async (medicineId: string) => {
    if (!confirm('Are you sure you want to delete this school medicine?')) return;

    try {
      const response = await authDelete(
        `/api/v1/medicines/school/${selectedSchoolId}/${medicineId}`,
        getAccessToken()
      );
      if (!response.ok) throw new Error('Failed to delete school medicine');
      setSuccessMessage('School medicine deleted successfully');
      loadSchoolMedicines();
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
        `${API_BASE_URL}/api/v1/medicines/school/${selectedSchoolId}/upload?created_by=${selectedCounsellorId}&replace_existing=${replaceExisting}`,
        getAccessToken(),
        {
          method: 'POST',
          body: formData,
        }
      );

      if (!response.ok) throw new Error('Failed to upload file');
      const result = await response.json();
      setSuccessMessage(
        `Upload complete: ${result.successful || 0} imported, ${result.failed || 0} failed`
      );
      setShowUploadModal(false);
      loadSchoolMedicines();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Medicine List Management</h1>
            <p className="text-sm text-gray-600 mt-1">
              {viewMode === 'counsellor-medicines'
                ? 'Manage personal medicine lists for counsellors'
                : viewMode === 'school-medicines'
                ? 'Manage school-wide shared medicine lists'
                : 'Review and process medicine matching feedback'}
            </p>
          </div>
          {viewMode === 'counsellor-medicines' && selectedCounsellorId && (
            <div className="flex gap-2">
              <button
                onClick={() => setShowUploadModal(true)}
                className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
              >
                Upload CSV
              </button>
              <button
                onClick={() => {
                  setEditingMedicine(null);
                  setShowMedicineModal(true);
                }}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
              >
                + Add Medicine
              </button>
            </div>
          )}
          {viewMode === 'school-medicines' && selectedSchoolId && (
            <div className="flex gap-2">
              <button
                onClick={() => setShowUploadModal(true)}
                className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
              >
                Upload CSV
              </button>
              <button
                onClick={() => {
                  setEditingMedicine(null);
                  setShowMedicineModal(true);
                }}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
              >
                + Add Medicine
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
            onClick={() => setViewMode('counsellor-medicines')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'counsellor-medicines'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Counsellor Medicines
          </button>
          <button
            onClick={() => setViewMode('school-medicines')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'school-medicines'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            School Medicines
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
      {(viewMode === 'counsellor-medicines' || viewMode === 'feedback-review') && (
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
            {counsellors.map(counsellor => (
              <option key={counsellor.id} value={counsellor.id} style={{ color: '#111827' }}>
                {counsellor.full_name} {counsellor.specialization ? `(${counsellor.specialization})` : ''}
              </option>
            ))}
          </select>
          {counsellors.length === 0 && (
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

      {/* Counsellor Medicines View */}
      {viewMode === 'counsellor-medicines' && selectedCounsellorId && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-200">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">
                Medicine List ({filteredMedicines.length} of {medicines.length})
              </h2>
              <select
                value={categoryFilter}
                onChange={(e) => {
                  setCategoryFilter(e.target.value);
                  loadCounsellorMedicines();
                }}
                className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
              >
                <option value="all">All Categories</option>
                {MEDICINE_CATEGORIES.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search medicines..."
              className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
            />
          </div>

          {loading ? (
            <div className="p-8 text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Loading medicines...</p>
            </div>
          ) : filteredMedicines.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <p>No medicines found</p>
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
                      Medicine Name
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Category
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Form
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
                  {filteredMedicines.map(medicine => (
                    <tr key={medicine.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="font-medium text-gray-900">{medicine.medicine_name}</div>
                          {medicine.external_id && (
                            <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                              #{medicine.external_id}
                            </span>
                          )}
                        </div>
                        {medicine.formulary_name && (
                          <div className="text-xs text-gray-500">{medicine.formulary_name}</div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {medicine.category || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {medicine.form || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {medicine.common_names?.join(', ') || '-'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          <button
                            onClick={() => {
                              setEditingMedicine(medicine);
                              setShowMedicineModal(true);
                            }}
                            className="text-blue-600 hover:text-blue-700 text-sm font-medium"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDeleteMedicine(medicine.id)}
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
              placeholder="Search by medicine name..."
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
                  medicines={medicines}
                  onSubmitFeedback={handleSubmitFeedback}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* School Selector */}
      {viewMode === 'school-medicines' && (
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
            {schools.map(school => (
              <option key={school.id} value={school.id} style={{ color: '#111827' }}>
                {school.school_name}
              </option>
            ))}
          </select>
          {schools.length === 0 && (
            <p className="text-sm text-amber-600 mt-2">
              No schools found. Make sure the backend is running and schools exist in the database.
            </p>
          )}
        </div>
      )}

      {/* School Medicines View */}
      {viewMode === 'school-medicines' && selectedSchoolId && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-200">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">
                School Medicine List ({schoolMedicines.length})
              </h2>
              <select
                value={categoryFilter}
                onChange={(e) => {
                  setCategoryFilter(e.target.value);
                  loadSchoolMedicines();
                }}
                className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
              >
                <option value="all">All Categories</option>
                {MEDICINE_CATEGORIES.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search medicines..."
              className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
            />
          </div>

          {loading ? (
            <div className="p-8 text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Loading school medicines...</p>
            </div>
          ) : filteredSchoolMedicines.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <p>No school medicines found</p>
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
                      Medicine Name
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Category
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Form
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
                  {filteredSchoolMedicines.map(medicine => (
                    <tr key={medicine.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="font-medium text-gray-900">{medicine.medicine_name}</div>
                          {medicine.external_id && (
                            <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                              #{medicine.external_id}
                            </span>
                          )}
                        </div>
                        {medicine.formulary_name && (
                          <div className="text-xs text-gray-500">{medicine.formulary_name}</div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {medicine.category || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {medicine.form || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {medicine.common_names?.join(', ') || '-'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          <button
                            onClick={() => {
                              setEditingMedicine(medicine);
                              setShowMedicineModal(true);
                            }}
                            className="text-blue-600 hover:text-blue-700 text-sm font-medium"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDeleteSchoolMedicine(medicine.id)}
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

      {/* Medicine Modal */}
      {showMedicineModal && (
        <MedicineModal
          medicine={editingMedicine}
          onClose={() => {
            setShowMedicineModal(false);
            setEditingMedicine(null);
          }}
          onSave={async (data) => {
            try {
              // Determine if we're in school or counsellor context
              const isSchoolContext = viewMode === 'school-medicines';

              if (isSchoolContext) {
                // School medicine save
                if (!selectedSchoolId) {
                  setError('Please select a school first');
                  return;
                }
                if (!selectedCounsellorId) {
                  setError('Please select a counsellor as admin for audit trail');
                  return;
                }

                const endpoint = editingMedicine
                  ? `/api/v1/medicines/school/${selectedSchoolId}/${editingMedicine.id}`
                  : `/api/v1/medicines/school/${selectedSchoolId}?created_by=${selectedCounsellorId}`;

                const response = editingMedicine
                  ? await authPut(endpoint, getAccessToken(), data)
                  : await authPost(endpoint, getAccessToken(), data);

                if (!response.ok) throw new Error('Failed to save school medicine');
                setSuccessMessage(editingMedicine ? 'School medicine updated' : 'School medicine added');
                setShowMedicineModal(false);
                setEditingMedicine(null);
                loadSchoolMedicines();
              } else {
                // Counsellor medicine save
                const endpoint = editingMedicine
                  ? `/api/v1/medicines/${selectedCounsellorId}/${editingMedicine.id}`
                  : `/api/v1/medicines/${selectedCounsellorId}`;

                const response = editingMedicine
                  ? await authPut(endpoint, getAccessToken(), data)
                  : await authPost(endpoint, getAccessToken(), data);

                if (!response.ok) throw new Error('Failed to save medicine');
                setSuccessMessage(editingMedicine ? 'Medicine updated' : 'Medicine added');
                setShowMedicineModal(false);
                setEditingMedicine(null);
                loadCounsellorMedicines();
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
          onUpload={viewMode === 'school-medicines' ? handleSchoolFileUpload : handleFileUpload}
          fileInputRef={fileInputRef}
          isSchoolUpload={viewMode === 'school-medicines'}
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
  medicines: Medicine[];
  onSubmitFeedback: (id: string, status: 'agreed' | 'disagreed', correctMedicineName?: string) => void;
}

function FeedbackRecordRow({ record, medicines, onSubmitFeedback }: FeedbackRecordRowProps) {
  const [showCorrection, setShowCorrection] = useState(false);
  const [correctName, setCorrectName] = useState('');

  const confidenceColor = (confidence?: number) => {
    if (!confidence) return 'bg-gray-100 text-gray-700';
    if (confidence >= 0.8) return 'bg-green-100 text-green-700';
    if (confidence >= 0.5) return 'bg-yellow-100 text-yellow-700';
    return 'bg-red-100 text-red-700';
  };

  return (
    <div className="p-4 hover:bg-gray-50">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium text-gray-900">{record.original_medicine_name}</span>
            <span className="text-gray-400">→</span>
            <span className={`font-medium ${record.matched_medicine_name ? 'text-blue-600' : 'text-red-600'}`}>
              {record.matched_medicine_name || 'No Match'}
            </span>
          </div>
          <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
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
            {record.diagnosis_context && (
              <span className="text-gray-500">Context: {record.diagnosis_context}</span>
            )}
          </div>
          {record.feedback_status && (
            <div className="mt-2">
              <span className={`text-xs px-2 py-0.5 rounded ${
                record.feedback_status === 'agreed' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
              }`}>
                {record.feedback_status.toUpperCase()}
                {record.correct_medicine_name && ` → ${record.correct_medicine_name}`}
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
                  placeholder="Correct medicine name"
                  className="px-2 py-1 border border-gray-300 rounded text-sm w-48 text-gray-900 bg-white"
                  list="medicine-suggestions"
                />
                <datalist id="medicine-suggestions">
                  {medicines.map(m => (
                    <option key={m.id} value={m.medicine_name} />
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

// Medicine Modal Component
interface MedicineModalProps {
  medicine: Medicine | null;
  onClose: () => void;
  onSave: (data: Partial<Medicine>) => void;
}

function MedicineModal({ medicine, onClose, onSave }: MedicineModalProps) {
  const [formData, setFormData] = useState({
    medicine_name: medicine?.medicine_name || '',
    common_names: medicine?.common_names?.join(', ') || '',
    category: medicine?.category || '',
    typical_dosage: medicine?.typical_dosage || '',
    form: medicine?.form || '',
    snomed_code: medicine?.snomed_code || '',
    formulary_name: medicine?.formulary_name || '',
    medicine_type: medicine?.medicine_type || '',
  });

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-200">
          <h2 className="text-xl font-bold text-gray-900">
            {medicine ? 'Edit Medicine' : 'Add Medicine'}
          </h2>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Medicine Name *
            </label>
            <input
              type="text"
              value={formData.medicine_name}
              onChange={(e) => setFormData({ ...formData, medicine_name: e.target.value })}
              placeholder="e.g., AMLODIPINE 5MG"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
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
                {MEDICINE_CATEGORIES.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Form
              </label>
              <select
                value={formData.form}
                onChange={(e) => setFormData({ ...formData, form: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
              >
                <option value="">Select form</option>
                {MEDICINE_FORMS.map(form => (
                  <option key={form} value={form}>{form}</option>
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
              placeholder="e.g., dolo tablet, dolo, paracetamol"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
            />
            <p className="text-xs text-gray-500 mt-1">
              Alternative names the counsellor commonly uses
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Typical Dosage
            </label>
            <input
              type="text"
              value={formData.typical_dosage}
              onChange={(e) => setFormData({ ...formData, typical_dosage: e.target.value })}
              placeholder="e.g., 5mg-10mg once daily"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                SNOMED Code
              </label>
              <input
                type="text"
                value={formData.snomed_code}
                onChange={(e) => setFormData({ ...formData, snomed_code: e.target.value })}
                placeholder="Optional"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Medicine Type
              </label>
              <select
                value={formData.medicine_type}
                onChange={(e) => setFormData({ ...formData, medicine_type: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
              >
                <option value="">Select type</option>
                <option value="generic">Generic</option>
                <option value="branded">Branded</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Formulary Name
            </label>
            <input
              type="text"
              value={formData.formulary_name}
              onChange={(e) => setFormData({ ...formData, formulary_name: e.target.value })}
              placeholder="Official formulary name (optional)"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
            />
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
            disabled={!formData.medicine_name}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {medicine ? 'Update' : 'Add'}
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
            {isSchoolUpload ? 'Upload School Medicine List' : 'Upload Medicine List'}
          </h2>
          {isSchoolUpload && (
            <p className="text-sm text-gray-600 mt-1">
              School medicines are shared across all counsellors in this school.
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
                    Uploading and importing medicines from CSV
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
                  name, common_name, category, typical_dosage, form, formulary_name, type
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-700 font-medium">Alternate Format (auto-mapped):</p>
                <p className="text-xs text-gray-600 font-mono">
                  BRAND ID, BRAND NAME, GENERIC NAME
                </p>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Column headers are case-insensitive. Only &quot;name&quot; or &quot;BRAND NAME&quot; is required.
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
                ? 'Replace all existing school medicines (instead of merging)'
                : 'Replace all existing medicines (instead of merging)'}
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
