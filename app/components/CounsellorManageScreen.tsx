"use client";

/**
 * Counsellor Management Screen
 *
 * CRUD for counsellors: view/edit details, create new counsellors, deactivate.
 * Two-panel layout similar to AssistantConfigScreen.
 */

import { useState, useEffect, useRef } from 'react';
import { useAuth } from '@lib/auth';
import {
  getCounsellors,
  getCounsellor,
  updateCounsellor,
  deactivateCounsellor,
  deleteCounsellorPermanently,
  createCounsellorForSchool,
  type Counsellor,
  type CreateCounsellorForSchoolRequest,
} from '@/services/counsellorApi';
import {
  getSchools,
  type School,
} from '@/services/schoolApi';

export default function CounsellorManageScreen() {
  const { getAccessToken } = useAuth();

  // Data
  const [counsellors, setCounsellors] = useState<Counsellor[]>([]);
  const [schools, setSchools] = useState<School[]>([]);
  const [selectedCounsellor, setSelectedCounsellor] = useState<Counsellor | null>(null);

  // Filters
  const [schoolFilter, setSchoolFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');

  // Loading
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Edit mode
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    full_name: '',
    email: '',
    specialization: '',
    translation_language: '',
  });

  // Create modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createForm, setCreateForm] = useState<CreateCounsellorForSchoolRequest>({
    school_code: '',
    full_name: '',
    email: '',
    specialization: '',
  });

  // Use ref to always access the latest getAccessToken without stale closures
  const getTokenRef = useRef(getAccessToken);
  getTokenRef.current = getAccessToken;

  const refreshCounsellors = async () => {
    const token = getTokenRef.current();
    const counsellorList = await getCounsellors(true, token);
    setCounsellors(counsellorList);
  };

  const refreshSchools = async () => {
    const token = getTokenRef.current();
    const schoolList = await getSchools(token);
    setSchools(schoolList);
  };

  // Load data on mount
  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const token = getTokenRef.current();
        const [counsellorList, schoolList] = await Promise.all([
          getCounsellors(true, token),
          getSchools(token),
        ]);
        if (!cancelled) {
          setCounsellors(counsellorList);
          setSchools(schoolList);
        }
      } catch (err) {
        console.error('CounsellorManageScreen load error:', err);
        if (!cancelled) {
          setError('Failed to load data: ' + (err as Error).message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => { cancelled = true; };
  }, []);

  const handleSelectCounsellor = async (counsellorId: string) => {
    setLoading(true);
    setError(null);
    setIsEditing(false);
    try {
      const token = getAccessToken();
      const doc = await getCounsellor(counsellorId, token);
      setSelectedCounsellor(doc);
      setEditForm({
        full_name: doc.full_name,
        email: doc.email,
        specialization: doc.specialization || '',
        translation_language: doc.translation_language || '',
      });
    } catch (err) {
      setError('Failed to load counsellor: ' + (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdate = async () => {
    if (!selectedCounsellor) return;
    setActionLoading('update');
    try {
      const token = getAccessToken();
      const updated = await updateCounsellor(selectedCounsellor.id, {
        full_name: editForm.full_name,
        email: editForm.email,
        specialization: editForm.specialization || undefined,
        translation_language: editForm.translation_language || undefined,
      }, token);
      setSelectedCounsellor(updated);
      setIsEditing(false);
      await refreshCounsellors();
    } catch (err) {
      alert('Failed to update counsellor: ' + (err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeactivate = async () => {
    if (!selectedCounsellor) return;
    if (!confirm(`Are you sure you want to deactivate ${selectedCounsellor.full_name}?`)) return;

    setActionLoading('deactivate');
    try {
      const token = getAccessToken();
      await deactivateCounsellor(selectedCounsellor.id, token);
      setSelectedCounsellor(null);
      await refreshCounsellors();
    } catch (err) {
      alert('Failed to deactivate counsellor: ' + (err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleHardDelete = async () => {
    if (!selectedCounsellor) return;
    if (!confirm(`PERMANENTLY DELETE "${selectedCounsellor.full_name}"? This cannot be undone!`)) return;
    if (!confirm(`Are you absolutely sure? All associated config data will be deleted.`)) return;

    setActionLoading('hard-delete');
    try {
      const token = getAccessToken();
      await deleteCounsellorPermanently(selectedCounsellor.id, token);
      setSelectedCounsellor(null);
      await refreshCounsellors();
    } catch (err) {
      alert('Failed to delete counsellor: ' + (err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleCreate = async () => {
    if (!createForm.school_code || !createForm.full_name || !createForm.email) {
      alert('Please fill in all required fields');
      return;
    }
    setActionLoading('create');
    try {
      const token = getAccessToken();
      const result = await createCounsellorForSchool(createForm, token);
      setShowCreateModal(false);
      setCreateForm({ school_code: '', full_name: '', email: '', specialization: '' });
      await refreshCounsellors();
      if (result.counsellor_id) {
        handleSelectCounsellor(result.counsellor_id);
      }
    } catch (err) {
      alert('Failed to create counsellor: ' + (err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  // Filtered counsellors
  const filteredCounsellors = counsellors.filter((d) => {
    const matchesSchool = !schoolFilter || d.school_id === schoolFilter;
    const matchesSearch =
      !searchQuery ||
      d.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.email.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSchool && matchesSearch;
  });

  // Get school name for a counsellor
  const getSchoolName = (schoolId: string | null) => {
    if (!schoolId) return 'Not assigned';
    const h = schools.find((h) => h.id === schoolId);
    return h?.school_name || 'Unknown';
  };

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2">Counsellor Management</h1>
        <p className="text-gray-300">Create, edit, and manage counsellor profiles</p>
      </div>

      {/* Filters + Create */}
      <div className="mb-8 bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">Filter by School</label>
            <select
              value={schoolFilter}
              onChange={(e) => setSchoolFilter(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
            >
              <option value="">All Schools</option>
              {schools.map((h) => (
                <option key={h.id} value={h.id}>{h.school_name}</option>
              ))}
            </select>
          </div>
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">Search</label>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name or email..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
            />
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2.5 bg-teal-600 text-white rounded-lg hover:bg-teal-700 transition-colors font-medium text-sm"
          >
            + Create Counsellor
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Counsellor List */}
        <div className="lg:col-span-1 bg-white rounded-lg shadow-sm border border-gray-200 p-4 max-h-[600px] overflow-y-auto">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Counsellors ({filteredCounsellors.length})
          </h2>

          {loading && !selectedCounsellor && (
            <div className="text-center py-8">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-gray-300 border-t-teal-600"></div>
            </div>
          )}

          {!loading && filteredCounsellors.length === 0 && (
            <p className="text-gray-500 text-sm text-center py-8">No counsellors found</p>
          )}

          <div className="space-y-2">
            {filteredCounsellors.map((d) => (
              <button
                key={d.id}
                onClick={() => handleSelectCounsellor(d.id)}
                className={`w-full text-left p-3 rounded-lg transition-colors ${
                  selectedCounsellor?.id === d.id
                    ? 'bg-teal-50 border border-teal-300'
                    : 'bg-gray-50 hover:bg-gray-100 border border-transparent'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-gray-900 text-sm">{d.full_name}</p>
                    <p className="text-xs text-gray-500">{d.email}</p>
                    {d.specialization && (
                      <p className="text-xs text-gray-400 mt-0.5">{d.specialization}</p>
                    )}
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    d.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                  }`}>
                    {d.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Right: Counsellor Details */}
        <div className="lg:col-span-2">
          {!selectedCounsellor ? (
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8 text-center">
              <svg className="w-16 h-16 mx-auto mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
              <p className="text-gray-500 font-medium">Select a counsellor to view details</p>
              <p className="text-gray-400 text-sm mt-1">Or create a new counsellor using the button above</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Details Panel */}
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-xl font-semibold text-gray-900">Counsellor Details</h2>
                  {!isEditing && (
                    <button
                      onClick={() => setIsEditing(true)}
                      className="text-teal-600 hover:text-teal-700 text-sm font-medium"
                    >
                      Edit
                    </button>
                  )}
                </div>

                {isEditing ? (
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
                      <input
                        type="text"
                        value={editForm.full_name}
                        onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                      <input
                        type="email"
                        value={editForm.email}
                        onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Specialization</label>
                      <input
                        type="text"
                        value={editForm.specialization}
                        onChange={(e) => setEditForm({ ...editForm, specialization: e.target.value })}
                        placeholder="e.g., Cardiology, Pediatrics"
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Translation Language</label>
                      <select
                        value={editForm.translation_language}
                        onChange={(e) => setEditForm({ ...editForm, translation_language: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                      >
                        <option value="">None (English only)</option>
                        <option value="tamil">Tamil</option>
                        <option value="hindi">Hindi</option>
                        <option value="telugu">Telugu</option>
                        <option value="kannada">Kannada</option>
                        <option value="malayalam">Malayalam</option>
                        <option value="bengali">Bengali</option>
                        <option value="marathi">Marathi</option>
                        <option value="gujarati">Gujarati</option>
                      </select>
                    </div>
                    <div className="flex gap-2 pt-2">
                      <button
                        onClick={handleUpdate}
                        disabled={actionLoading === 'update'}
                        className="px-4 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:bg-gray-300 font-medium transition-colors"
                      >
                        {actionLoading === 'update' ? 'Saving...' : 'Save'}
                      </button>
                      <button
                        onClick={() => {
                          setIsEditing(false);
                          setEditForm({
                            full_name: selectedCounsellor.full_name,
                            email: selectedCounsellor.email,
                            specialization: selectedCounsellor.specialization || '',
                            translation_language: selectedCounsellor.translation_language || '',
                          });
                        }}
                        className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div>
                      <p className="text-sm text-gray-500">Full Name</p>
                      <p className="text-gray-900 font-medium">{selectedCounsellor.full_name}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Email</p>
                      <p className="text-gray-900">{selectedCounsellor.email}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Specialization</p>
                      <p className="text-gray-900">{selectedCounsellor.specialization || 'Not specified'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Translation Language</p>
                      <p className="text-gray-900">{selectedCounsellor.translation_language ? selectedCounsellor.translation_language.charAt(0).toUpperCase() + selectedCounsellor.translation_language.slice(1) : 'None'}</p>
                    </div>
                  </div>
                )}

                {/* Deactivate / Delete */}
                {!isEditing && (
                  <div className="mt-6 pt-6 border-t border-gray-200 flex gap-3">
                    {selectedCounsellor.is_active && (
                      <button
                        onClick={handleDeactivate}
                        disabled={actionLoading === 'deactivate'}
                        className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:bg-gray-300 text-sm font-medium transition-colors"
                      >
                        {actionLoading === 'deactivate' ? 'Deactivating...' : 'Deactivate'}
                      </button>
                    )}
                    <button
                      onClick={handleHardDelete}
                      disabled={actionLoading === 'hard-delete'}
                      className="px-4 py-2 border-2 border-red-600 text-red-600 rounded-lg hover:bg-red-50 disabled:border-gray-300 disabled:text-gray-300 text-sm font-medium transition-colors"
                    >
                      {actionLoading === 'hard-delete' ? 'Deleting...' : 'Delete Permanently'}
                    </button>
                  </div>
                )}
              </div>

              {/* Status Panel */}
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <h2 className="text-xl font-semibold text-gray-900 mb-6">Status Info</h2>
                <div className="space-y-4">
                  <div>
                    <p className="text-sm text-gray-500">Status</p>
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      selectedCounsellor.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                    }`}>
                      {selectedCounsellor.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">School</p>
                    <p className="text-gray-900">{getSchoolName(selectedCounsellor.school_id)}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Created</p>
                    <p className="text-gray-900 text-sm">
                      {new Date(selectedCounsellor.created_at).toLocaleDateString('en-IN', {
                        day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
                      })}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Updated</p>
                    <p className="text-gray-900 text-sm">
                      {new Date(selectedCounsellor.updated_at).toLocaleDateString('en-IN', {
                        day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
                      })}
                    </p>
                  </div>
                  {selectedCounsellor.last_login_at && (
                    <div>
                      <p className="text-sm text-gray-500">Last Login</p>
                      <p className="text-gray-900 text-sm">
                        {new Date(selectedCounsellor.last_login_at).toLocaleDateString('en-IN', {
                          day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
                        })}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Create Counsellor Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-6">Create Counsellor</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">School *</label>
                <select
                  value={createForm.school_code}
                  onChange={(e) => setCreateForm({ ...createForm, school_code: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                >
                  <option value="">Select school...</option>
                  {schools.map((h) => (
                    <option key={h.id} value={h.school_code || ''}>
                      {h.school_name} ({h.school_code})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Full Name *</label>
                <input
                  type="text"
                  value={createForm.full_name}
                  onChange={(e) => setCreateForm({ ...createForm, full_name: e.target.value })}
                  placeholder="John Smith"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email *</label>
                <input
                  type="email"
                  value={createForm.email}
                  onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                  placeholder="counsellor@school.com"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Specialization</label>
                <input
                  type="text"
                  value={createForm.specialization || ''}
                  onChange={(e) => setCreateForm({ ...createForm, specialization: e.target.value })}
                  placeholder="e.g., Cardiology, Pediatrics"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={handleCreate}
                disabled={actionLoading === 'create'}
                className="flex-1 px-4 py-2.5 bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:bg-gray-300 font-medium transition-colors"
              >
                {actionLoading === 'create' ? 'Creating...' : 'Create Counsellor'}
              </button>
              <button
                onClick={() => {
                  setShowCreateModal(false);
                  setCreateForm({ school_code: '', full_name: '', email: '', specialization: '' });
                }}
                className="px-4 py-2.5 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
