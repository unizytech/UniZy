"use client";

/**
 * Assistant Configuration Screen
 *
 * Manages assistant profiles and their template access:
 * 1. View/Edit assistant details (name, email, qualification, school)
 * 2. Link/Unlink counsellors to assistants
 * 3. View/Activate/Deactivate templates shared with the assistant
 * 4. Create new assistants
 */

import { useState, useEffect } from 'react';
import AssistantSelector from './AssistantSelector';
import CreateAssistantModal from './CreateAssistantModal';
import { useAuth } from '@lib/auth';
import {
  getAssistant,
  updateAssistant,
  deactivateAssistant,
  getAssistantCounsellors,
  linkAssistantToCounsellor,
  unlinkAssistantFromCounsellor,
  getAssistantTemplates,
  activateAssistantTemplate,
  deactivateAssistantTemplate,
  type Assistant,
  type AssistantTemplate,
  type AssistantCounsellor
} from '@/services/assistantApi';
import { getCounsellors } from '@/services/counsellorApi';

interface Counsellor {
  id: string;
  full_name: string;
  email: string;
  specialization?: string | null;
}

export default function AssistantConfigScreen() {
  const { getAccessToken } = useAuth();
  const [selectedAssistantId, setSelectedAssistantId] = useState<string | null>(null);
  const [nurse, setAssistant] = useState<Assistant | null>(null);
  const [linkedCounsellors, setLinkedCounsellors] = useState<AssistantCounsellor[]>([]);
  const [templates, setTemplates] = useState<AssistantTemplate[]>([]);
  const [allCounsellors, setAllCounsellors] = useState<Counsellor[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    full_name: '',
    email: '',
    qualification: ''
  });

  // Link counsellor dropdown
  const [selectedCounsellorToLink, setSelectedCounsellorToLink] = useState<string>('');

  // Load assistant data when selected
  useEffect(() => {
    if (selectedAssistantId) {
      loadAssistantData();
    } else {
      setAssistant(null);
      setLinkedCounsellors([]);
      setTemplates([]);
    }
  }, [selectedAssistantId]);

  // Load all counsellors for linking dropdown
  useEffect(() => {
    loadAllCounsellors();
  }, []);

  const loadAllCounsellors = async () => {
    try {
      const token = getAccessToken();
      const doctors = await getCounsellors(true, token);
      setAllCounsellors(doctors);
    } catch (err) {
      console.error('Failed to load counsellors:', err);
    }
  };

  const loadAssistantData = async () => {
    if (!selectedAssistantId) return;

    setLoading(true);
    setError(null);

    try {
      const token = getAccessToken();
      const [nurseData, doctorsData, templatesData] = await Promise.all([
        getAssistant(selectedAssistantId, token),
        getAssistantCounsellors(selectedAssistantId, token),
        getAssistantTemplates(selectedAssistantId, token)
      ]);

      setAssistant(nurseData);
      setLinkedCounsellors(doctorsData);
      setTemplates(templatesData);

      // Initialize edit form
      setEditForm({
        full_name: nurseData.full_name,
        email: nurseData.email,
        qualification: nurseData.qualification || ''
      });
    } catch (err) {
      setError('Failed to load assistant data: ' + (err as Error).message);
      console.error('Failed to load assistant data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateAssistant = async () => {
    if (!selectedAssistantId || !nurse) return;

    setActionLoading('update');
    try {
      const token = getAccessToken();
      await updateAssistant(selectedAssistantId, {
        full_name: editForm.full_name,
        email: editForm.email,
        qualification: editForm.qualification || undefined
      }, token);
      setIsEditing(false);
      loadAssistantData();
    } catch (err) {
      alert('Failed to update assistant: ' + (err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeactivateAssistant = async () => {
    if (!selectedAssistantId || !nurse) return;

    if (!confirm(`Are you sure you want to deactivate ${nurse.full_name}? They will no longer be able to record or access templates.`)) {
      return;
    }

    setActionLoading('deactivate');
    try {
      const token = getAccessToken();
      await deactivateAssistant(selectedAssistantId, token);
      setSelectedAssistantId(null);
      alert('Assistant deactivated successfully');
    } catch (err) {
      alert('Failed to deactivate assistant: ' + (err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleLinkCounsellor = async () => {
    if (!selectedAssistantId || !selectedCounsellorToLink) return;

    setActionLoading('link');
    try {
      const token = getAccessToken();
      await linkAssistantToCounsellor(selectedAssistantId, selectedCounsellorToLink, token);
      setSelectedCounsellorToLink('');
      loadAssistantData();
    } catch (err) {
      alert('Failed to link counsellor: ' + (err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleUnlinkCounsellor = async (doctorId: string) => {
    if (!selectedAssistantId) return;

    setActionLoading(`unlink-${doctorId}`);
    try {
      const token = getAccessToken();
      await unlinkAssistantFromCounsellor(selectedAssistantId, doctorId, token);
      loadAssistantData();
    } catch (err) {
      alert('Failed to unlink counsellor: ' + (err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleActivateTemplate = async (templateId: string) => {
    if (!selectedAssistantId) return;

    setActionLoading(`activate-${templateId}`);
    try {
      const token = getAccessToken();
      await activateAssistantTemplate(selectedAssistantId, templateId, token);
      loadAssistantData();
    } catch (err) {
      alert('Failed to activate template: ' + (err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeactivateTemplate = async (templateId: string) => {
    if (!selectedAssistantId) return;

    setActionLoading(`deactivate-${templateId}`);
    try {
      const token = getAccessToken();
      await deactivateAssistantTemplate(selectedAssistantId, templateId, token);
      loadAssistantData();
    } catch (err) {
      alert('Failed to deactivate template: ' + (err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  // Filter out already linked counsellors from the dropdown
  const availableCounsellorsToLink = allCounsellors.filter(
    d => !linkedCounsellors.some(ld => ld.counsellor_id === d.id)
  );

  // Separate active and inactive templates
  const activeTemplates = templates.filter(t => t.is_active);
  const inactiveTemplates = templates.filter(t => !t.is_active);

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2">
          Assistant Configuration
        </h1>
        <p className="text-gray-300">
          Manage assistant profiles, counsellor links, and template access
        </p>
      </div>

      {/* Assistant Selector + Create Button */}
      <div className="mb-8 bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <div className="flex items-end gap-4">
          <div className="flex-1 max-w-md">
            <AssistantSelector
              selectedAssistantId={selectedAssistantId}
              onAssistantSelect={setSelectedAssistantId}
            />
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-3 bg-teal-600 text-white rounded-lg hover:bg-teal-700 transition-colors font-medium"
          >
            + Create Assistant
          </button>
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-gray-300 border-t-teal-600"></div>
          <p className="mt-4 text-gray-600">Loading assistant data...</p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-8">
          <p className="text-red-800">{error}</p>
          <button
            onClick={loadAssistantData}
            className="mt-2 text-sm text-red-600 hover:text-red-700 underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Main Content */}
      {selectedAssistantId && nurse && !loading && !error && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* LEFT PANEL: Assistant Details */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold text-gray-900">
                Assistant Details
              </h2>
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
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Full Name
                  </label>
                  <input
                    type="text"
                    value={editForm.full_name}
                    onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Email
                  </label>
                  <input
                    type="email"
                    value={editForm.email}
                    onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Qualification
                  </label>
                  <input
                    type="text"
                    value={editForm.qualification}
                    onChange={(e) => setEditForm({ ...editForm, qualification: e.target.value })}
                    placeholder="e.g., RN, BSN, LPN"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>
                <div className="flex gap-2 pt-2">
                  <button
                    onClick={handleUpdateAssistant}
                    disabled={actionLoading === 'update'}
                    className="px-4 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:bg-gray-300 font-medium transition-colors"
                  >
                    {actionLoading === 'update' ? 'Saving...' : 'Save'}
                  </button>
                  <button
                    onClick={() => {
                      setIsEditing(false);
                      setEditForm({
                        full_name: nurse.full_name,
                        email: nurse.email,
                        qualification: nurse.qualification || ''
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
                  <p className="text-gray-900 font-medium">{nurse.full_name}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Email</p>
                  <p className="text-gray-900">{nurse.email}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Qualification</p>
                  <p className="text-gray-900">{nurse.qualification || 'Not specified'}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Status</p>
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    nurse.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                  }`}>
                    {nurse.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
              </div>
            )}

            {/* Deactivate Button */}
            {!isEditing && nurse.is_active && (
              <div className="mt-6 pt-6 border-t border-gray-200">
                <button
                  onClick={handleDeactivateAssistant}
                  disabled={actionLoading === 'deactivate'}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:bg-gray-300 text-sm font-medium transition-colors"
                >
                  {actionLoading === 'deactivate' ? 'Deactivating...' : 'Deactivate Assistant'}
                </button>
              </div>
            )}

            {/* Linked Counsellors Section */}
            <div className="mt-6 pt-6 border-t border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                Linked Counsellors ({linkedCounsellors.length})
              </h3>

              {/* Link Counsellor Dropdown */}
              {availableCounsellorsToLink.length > 0 && (
                <div className="flex gap-2 mb-4">
                  <select
                    value={selectedCounsellorToLink}
                    onChange={(e) => setSelectedCounsellorToLink(e.target.value)}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-gray-900 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  >
                    <option value="">Select counsellor to link...</option>
                    {availableCounsellorsToLink.map((doctor) => (
                      <option key={doctor.id} value={doctor.id}>
                        {doctor.full_name} {doctor.specialization ? `(${doctor.specialization})` : ''}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={handleLinkCounsellor}
                    disabled={!selectedCounsellorToLink || actionLoading === 'link'}
                    className="px-4 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-sm font-medium transition-colors"
                  >
                    {actionLoading === 'link' ? 'Linking...' : 'Link'}
                  </button>
                </div>
              )}

              {/* Linked Counsellors List */}
              {linkedCounsellors.length === 0 ? (
                <p className="text-gray-500 text-sm">No counsellors linked to this assistant</p>
              ) : (
                <div className="space-y-2">
                  {linkedCounsellors.map((link) => (
                    <div
                      key={link.counsellor_id}
                      className="flex items-center justify-between bg-gray-50 rounded-lg p-3"
                    >
                      <div>
                        <p className="font-medium text-gray-900">{link.counsellor_name}</p>
                        <p className="text-xs text-gray-500">{link.specialization || 'No specialization'}</p>
                      </div>
                      <button
                        onClick={() => handleUnlinkCounsellor(link.counsellor_id)}
                        disabled={actionLoading === `unlink-${link.counsellor_id}`}
                        className="text-red-600 hover:text-red-700 text-sm font-medium"
                      >
                        {actionLoading === `unlink-${link.counsellor_id}` ? 'Unlinking...' : 'Unlink'}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* RIGHT PANEL: Templates */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-6">
              Accessible Templates ({templates.length})
            </h2>

            {templates.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                <svg className="w-16 h-16 mx-auto mb-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="font-medium">No Templates Shared</p>
                <p className="text-sm mt-1">Share templates with this assistant from the Config screen</p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Active Templates */}
                {activeTemplates.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">
                      Active Templates
                    </h3>
                    <div className="space-y-2">
                      {activeTemplates.map((template) => (
                        <div
                          key={template.id}
                          className="flex items-center justify-between bg-green-50 border border-green-200 rounded-lg p-3"
                        >
                          <div className="flex-1">
                            <p className="font-medium text-gray-900">{template.template_name}</p>
                            <p className="text-xs text-gray-500">{template.template_code}</p>
                          </div>
                          <button
                            onClick={() => handleDeactivateTemplate(template.template_id)}
                            disabled={actionLoading === `deactivate-${template.template_id}`}
                            className="px-3 py-1.5 bg-yellow-500 text-white rounded-lg hover:bg-yellow-600 text-sm font-medium transition-colors"
                          >
                            {actionLoading === `deactivate-${template.template_id}` ? '...' : 'Remove'}
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Inactive Templates */}
                {inactiveTemplates.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">
                      Removed Templates
                    </h3>
                    <div className="space-y-2">
                      {inactiveTemplates.map((template) => (
                        <div
                          key={template.id}
                          className="flex items-center justify-between bg-gray-50 border border-gray-200 rounded-lg p-3"
                        >
                          <div className="flex-1">
                            <p className="font-medium text-gray-900">{template.template_name}</p>
                            <p className="text-xs text-gray-500">{template.template_code}</p>
                          </div>
                          <button
                            onClick={() => handleActivateTemplate(template.template_id)}
                            disabled={actionLoading === `activate-${template.template_id}`}
                            className="px-3 py-1.5 bg-teal-600 text-white rounded-lg hover:bg-teal-700 text-sm font-medium transition-colors"
                          >
                            {actionLoading === `activate-${template.template_id}` ? '...' : 'Re-add'}
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Help Text */}
            <div className="mt-6 pt-6 border-t border-gray-200">
              <p className="text-xs text-gray-500">
                <strong>Active templates</strong> are available in VSR screen when this assistant is selected.
                Use Remove/Re-add to manage which templates appear for this assistant.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Instructions when no assistant selected */}
      {!selectedAssistantId && !loading && (
        <div className="bg-teal-50 border border-teal-200 rounded-lg p-6">
          <h3 className="font-semibold text-teal-900 mb-2">Getting Started</h3>
          <ul className="text-sm text-teal-800 space-y-1.5">
            <li>
              <strong>Select an assistant</strong> from the dropdown to view and manage their profile
            </li>
            <li>
              <strong>Create a new assistant</strong> using the button above
            </li>
            <li>
              <strong>Link counsellors</strong> to assistants to establish recording relationships
            </li>
            <li>
              <strong>Share templates</strong> with assistants from the Config screen, then activate them here
            </li>
          </ul>
        </div>
      )}

      {/* Create Assistant Modal */}
      {showCreateModal && (
        <CreateAssistantModal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          onCreated={(nurseId) => {
            setShowCreateModal(false);
            setSelectedAssistantId(nurseId);
          }}
        />
      )}
    </div>
  );
}
