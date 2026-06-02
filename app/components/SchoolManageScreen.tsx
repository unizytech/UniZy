"use client";

/**
 * School Management Screen
 *
 * CRUD for schools: list, create, edit name/code, deactivate.
 */

import { useState, useEffect, useRef } from 'react';
import { useAuth } from '@lib/auth';
import {
  getSchools,
  createSchool,
  updateSchool,
  deactivateSchool,
  deleteSchoolPermanently,
  getSchoolFeatures,
  updateSchoolFeatures,
  type School,
} from '@/services/schoolApi';
import { FEATURE_FLAG_LABELS } from '@lib/types';

export default function SchoolManageScreen() {
  const { getAccessToken, isSuperAdmin } = useAuth();

  const [schools, setSchools] = useState<School[]>([]);
  const [selectedSchool, setSelectedSchool] = useState<School | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Edit mode
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({ school_name: '', school_code: '' });

  // Create mode
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ school_name: '', school_code: '' });

  // Feature flags modal
  const [showFeatureFlags, setShowFeatureFlags] = useState(false);
  const [featureFlags, setFeatureFlags] = useState<Record<string, boolean>>({});
  const [featureFlagsLoading, setFeatureFlagsLoading] = useState(false);
  const [featureFlagsSaving, setFeatureFlagsSaving] = useState(false);
  const [newFlagKey, setNewFlagKey] = useState('');

  // Use ref to always access the latest getAccessToken
  const getTokenRef = useRef(getAccessToken);
  getTokenRef.current = getAccessToken;

  const refreshSchools = async () => {
    const token = getTokenRef.current();
    const list = await getSchools(token);
    setSchools(list);
  };

  // Load schools on mount
  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const token = getTokenRef.current();
        const list = await getSchools(token);
        if (!cancelled) setSchools(list);
      } catch (err) {
        console.error('SchoolManageScreen load error:', err);
        if (!cancelled) setError('Failed to load schools: ' + (err as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => { cancelled = true; };
  }, []);

  const handleSelect = (school: School) => {
    setSelectedSchool(school);
    setIsEditing(false);
    setEditForm({
      school_name: school.school_name,
      school_code: school.school_code || '',
    });
  };

  const handleUpdate = async () => {
    if (!selectedSchool) return;
    setActionLoading('update');
    try {
      const token = getAccessToken();
      const updated = await updateSchool(selectedSchool.id, {
        school_name: editForm.school_name,
        school_code: editForm.school_code,
      }, token);
      setSelectedSchool({ ...selectedSchool, ...updated });
      setIsEditing(false);
      await refreshSchools();
    } catch (err) {
      alert('Failed to update school: ' + (err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeactivate = async () => {
    if (!selectedSchool) return;
    if (!confirm(`Are you sure you want to deactivate "${selectedSchool.school_name}"? This will hide it from active lists.`)) return;

    setActionLoading('deactivate');
    try {
      const token = getAccessToken();
      await deactivateSchool(selectedSchool.id, token);
      setSelectedSchool(null);
      await refreshSchools();
    } catch (err) {
      alert('Failed to deactivate school: ' + (err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleHardDelete = async () => {
    if (!selectedSchool) return;
    if (!confirm(`PERMANENTLY DELETE "${selectedSchool.school_name}"? This cannot be undone!`)) return;
    if (!confirm(`Are you absolutely sure? All associated config data will be deleted.`)) return;

    setActionLoading('hard-delete');
    try {
      const token = getAccessToken();
      await deleteSchoolPermanently(selectedSchool.id, token);
      setSelectedSchool(null);
      await refreshSchools();
    } catch (err) {
      alert('Failed to delete school: ' + (err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleCreate = async () => {
    if (!createForm.school_code || !createForm.school_name) {
      alert('Please fill in all fields');
      return;
    }
    setActionLoading('create');
    try {
      const token = getAccessToken();
      await createSchool(createForm, token);
      setShowCreate(false);
      setCreateForm({ school_name: '', school_code: '' });
      await refreshSchools();
    } catch (err) {
      alert('Failed to create school: ' + (err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleOpenFeatureFlags = async () => {
    if (!selectedSchool) return;
    setShowFeatureFlags(true);
    setFeatureFlagsLoading(true);
    try {
      const token = getAccessToken();
      const flags = await getSchoolFeatures(selectedSchool.id, token);
      setFeatureFlags(flags);
    } catch (err) {
      alert('Failed to load feature flags: ' + (err as Error).message);
      setShowFeatureFlags(false);
    } finally {
      setFeatureFlagsLoading(false);
    }
  };

  const handleToggleFlag = (key: string) => {
    setFeatureFlags(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleAddNewFlag = () => {
    const key = newFlagKey.trim().toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
    if (!key) return;
    if (key in featureFlags) {
      alert(`Feature "${key}" already exists`);
      return;
    }
    setFeatureFlags(prev => ({ ...prev, [key]: false }));
    setNewFlagKey('');
  };

  const handleRemoveFlag = (key: string) => {
    // Only allow removing custom flags (not in FEATURE_FLAG_LABELS)
    if (key in FEATURE_FLAG_LABELS) return;
    setFeatureFlags(prev => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const handleSaveFeatureFlags = async () => {
    if (!selectedSchool) return;
    setFeatureFlagsSaving(true);
    try {
      const token = getAccessToken();
      const saved = await updateSchoolFeatures(selectedSchool.id, featureFlags, token);
      setFeatureFlags(saved);
      setShowFeatureFlags(false);
    } catch (err) {
      alert('Failed to save feature flags: ' + (err as Error).message);
    } finally {
      setFeatureFlagsSaving(false);
    }
  };

  const filteredSchools = schools.filter((h) =>
    !searchQuery ||
    h.school_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (h.school_code || '').toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2">School Management</h1>
        <p className="text-gray-300">Create, edit, and manage schools</p>
      </div>

      {/* Search + Create */}
      <div className="mb-8 bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <div className="flex items-end gap-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">Search</label>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name or code..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
            />
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2.5 bg-teal-600 text-white rounded-lg hover:bg-teal-700 transition-colors font-medium text-sm"
          >
            + Create School
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-gray-300 border-t-teal-600"></div>
          <p className="mt-4 text-gray-600">Loading schools...</p>
        </div>
      )}

      {/* Main Content */}
      {!loading && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: School List */}
          <div className="lg:col-span-1 bg-white rounded-lg shadow-sm border border-gray-200 p-4 max-h-[600px] overflow-y-auto">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Schools ({filteredSchools.length})
            </h2>

            {filteredSchools.length === 0 && (
              <p className="text-gray-500 text-sm text-center py-8">No schools found</p>
            )}

            <div className="space-y-2">
              {filteredSchools.map((h) => (
                <button
                  key={h.id}
                  onClick={() => handleSelect(h)}
                  className={`w-full text-left p-3 rounded-lg transition-colors ${
                    selectedSchool?.id === h.id
                      ? 'bg-teal-50 border border-teal-300'
                      : 'bg-gray-50 hover:bg-gray-100 border border-transparent'
                  }`}
                >
                  <p className="font-medium text-gray-900 text-sm">{h.school_name}</p>
                  <p className="text-xs text-gray-500">{h.school_code || 'No code'}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Right: School Details */}
          <div className="lg:col-span-2">
            {!selectedSchool ? (
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8 text-center">
                <svg className="w-16 h-16 mx-auto mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
                <p className="text-gray-500 font-medium">Select a school to view details</p>
                <p className="text-gray-400 text-sm mt-1">Or create a new school using the button above</p>
              </div>
            ) : (
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-xl font-semibold text-gray-900">School Details</h2>
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
                      <label className="block text-sm font-medium text-gray-700 mb-1">School Name</label>
                      <input
                        type="text"
                        value={editForm.school_name}
                        onChange={(e) => setEditForm({ ...editForm, school_name: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">School Code</label>
                      <input
                        type="text"
                        value={editForm.school_code}
                        onChange={(e) => setEditForm({ ...editForm, school_code: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                      />
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
                            school_name: selectedSchool.school_name,
                            school_code: selectedSchool.school_code || '',
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
                      <p className="text-sm text-gray-500">School Name</p>
                      <p className="text-gray-900 font-medium">{selectedSchool.school_name}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">School Code</p>
                      <p className="text-gray-900">{selectedSchool.school_code || 'Not set'}</p>
                    </div>
                    {selectedSchool.city && (
                      <div>
                        <p className="text-sm text-gray-500">Location</p>
                        <p className="text-gray-900">
                          {selectedSchool.city}{selectedSchool.state ? `, ${selectedSchool.state}` : ''}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {/* Feature Flags Button (super_admin only) */}
                {!isEditing && isSuperAdmin && (
                  <div className="mt-6 pt-6 border-t border-gray-200">
                    <button
                      onClick={handleOpenFeatureFlags}
                      className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors text-sm font-medium"
                    >
                      Feature Flags
                    </button>
                  </div>
                )}

                {/* Deactivate / Delete */}
                {!isEditing && (
                  <div className="mt-6 pt-6 border-t border-gray-200 flex gap-3">
                    <button
                      onClick={handleDeactivate}
                      disabled={actionLoading === 'deactivate'}
                      className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:bg-gray-300 text-sm font-medium transition-colors"
                    >
                      {actionLoading === 'deactivate' ? 'Deactivating...' : 'Deactivate'}
                    </button>
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
            )}
          </div>
        </div>
      )}

      {/* Create School Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-6">Create School</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">School Name *</label>
                <input
                  type="text"
                  value={createForm.school_name}
                  onChange={(e) => setCreateForm({ ...createForm, school_name: e.target.value })}
                  placeholder="City General School"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">School Code *</label>
                <input
                  type="text"
                  value={createForm.school_code}
                  onChange={(e) => setCreateForm({ ...createForm, school_code: e.target.value })}
                  placeholder="HOSP001"
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
                {actionLoading === 'create' ? 'Creating...' : 'Create School'}
              </button>
              <button
                onClick={() => {
                  setShowCreate(false);
                  setCreateForm({ school_name: '', school_code: '' });
                }}
                className="px-4 py-2.5 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Feature Flags Modal */}
      {showFeatureFlags && selectedSchool && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 p-6 max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900">
                Feature Flags — {selectedSchool.school_name}
              </h2>
              <button
                onClick={() => setShowFeatureFlags(false)}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
              >
                &times;
              </button>
            </div>

            {featureFlagsLoading ? (
              <div className="flex-1 flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-2 border-gray-300 border-t-indigo-600"></div>
              </div>
            ) : (
              <>
                <div className="flex-1 overflow-y-auto space-y-1 mb-4">
                  {Object.entries(featureFlags)
                    .sort(([a], [b]) => {
                      // Known flags first (sorted by label), then custom flags
                      const aKnown = a in FEATURE_FLAG_LABELS;
                      const bKnown = b in FEATURE_FLAG_LABELS;
                      if (aKnown && !bKnown) return -1;
                      if (!aKnown && bKnown) return 1;
                      const aLabel = FEATURE_FLAG_LABELS[a] || a;
                      const bLabel = FEATURE_FLAG_LABELS[b] || b;
                      return aLabel.localeCompare(bLabel);
                    })
                    .map(([key, enabled]) => {
                      const isCustom = !(key in FEATURE_FLAG_LABELS);
                      return (
                        <div
                          key={key}
                          className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-gray-50"
                        >
                          <div className="flex items-center gap-3 flex-1 min-w-0">
                            <label className="relative inline-flex items-center cursor-pointer">
                              <input
                                type="checkbox"
                                checked={enabled}
                                onChange={() => handleToggleFlag(key)}
                                className="sr-only peer"
                              />
                              <div className="w-9 h-5 bg-gray-200 peer-focus:ring-2 peer-focus:ring-indigo-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-600"></div>
                            </label>
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-gray-900 truncate">
                                {FEATURE_FLAG_LABELS[key] || key}
                              </p>
                              <p className="text-xs text-gray-400 font-mono">{key}</p>
                            </div>
                          </div>
                          {isCustom && (
                            <button
                              onClick={() => handleRemoveFlag(key)}
                              className="ml-2 text-red-400 hover:text-red-600 text-sm flex-shrink-0"
                              title="Remove custom flag"
                            >
                              &times;
                            </button>
                          )}
                        </div>
                      );
                    })}
                </div>

                {/* Add new feature flag */}
                <div className="border-t border-gray-200 pt-4 mb-4">
                  <p className="text-xs font-medium text-gray-500 mb-2">Add Custom Feature</p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newFlagKey}
                      onChange={(e) => setNewFlagKey(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleAddNewFlag()}
                      placeholder="e.g. video_consult"
                      className="flex-1 px-3 py-1.5 border border-gray-300 rounded-lg text-gray-900 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 font-mono"
                    />
                    <button
                      onClick={handleAddNewFlag}
                      disabled={!newFlagKey.trim()}
                      className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-40 text-sm font-medium transition-colors"
                    >
                      Add
                    </button>
                  </div>
                </div>

                <div className="flex gap-3">
                  <button
                    onClick={handleSaveFeatureFlags}
                    disabled={featureFlagsSaving}
                    className="flex-1 px-4 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:bg-gray-300 font-medium transition-colors"
                  >
                    {featureFlagsSaving ? 'Saving...' : 'Save Changes'}
                  </button>
                  <button
                    onClick={() => setShowFeatureFlags(false)}
                    className="px-4 py-2.5 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
