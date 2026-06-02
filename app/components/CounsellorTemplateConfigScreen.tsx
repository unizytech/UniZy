"use client";

/**
 * Counsellor Template Configuration Screen - Dual View
 *
 * Shows counsellors:
 * 1. LEFT PANEL: Visible Consultation Types (can activate to create owned template)
 * 2. RIGHT PANEL: Accessible Templates (owned, shared, global with clone option)
 *
 * Actions:
 * - Activate from Consultation Type → Creates new counsellor-owned template (auto-activated)
 * - Clone Template → Creates customizable copy (auto-activated)
 *
 * Auto-Activation:
 * - Templates created from consultation types are auto-activated
 * - Templates cloned are auto-activated
 * - Templates shared with 'use' access are auto-activated by backend
 *
 * VHRScreen will only show activated templates (is_active=true).
 */

import { useState, useEffect } from 'react';
import CounsellorSelector from './CounsellorSelector';
import { TemplateSegmentConfigPanel } from './TemplateSegmentConfigPanel';
import { ViewTemplateDetailsModal } from './ViewTemplateDetailsModal';
import { useAuth } from '@lib/auth';
import {
  getCounsellorDashboard,
  activateFromConsultationType,
  cloneTemplate,
  deleteTemplate,
  handleApiError,
} from '@lib/summaryApi';
import { getCounsellor, setCounsellorDefaultTemplate } from '@/services/counsellorApi';

interface ConsultationType {
  id: string;
  type_code: string;
  type_name: string;
  description?: string;
  icon_name?: string;
  color_code?: string;
  access_type: string;
  badge: string;
}

interface Template {
  id: string;
  template_code: string;
  template_name: string;
  consultation_type_id: string;
  access_type: 'owner' | 'shared' | 'common';
  is_active: boolean;
  badge: string;
  consultation_types?: {
    type_code: string;
    type_name: string;
  };
}

export default function CounsellorTemplateConfigScreen() {
  const { getAccessToken } = useAuth();
  const [selectedCounsellorId, setSelectedCounsellorId] = useState<string | null>(null);
  const [consultationTypes, setConsultationTypes] = useState<ConsultationType[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Dropdown states
  const [selectedConsultationTypeId, setSelectedConsultationTypeId] = useState<string | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);

  // Modal states
  const [configuringTemplate, setConfiguringTemplate] = useState<Template | null>(null);
  const [viewingTemplate, setViewingTemplate] = useState<Template | null>(null);

  // Default-template state — separate from template.is_default which is a
  // template-level column unrelated to the counsellor's chosen default. We track
  // counsellor.default_template_id directly and compare per-row.
  const [defaultTemplateId, setDefaultTemplateId] = useState<string | null>(null);
  const [updatingDefaultId, setUpdatingDefaultId] = useState<string | null>(null);

  // Ready-to-use templates (all active templates)
  const readyTemplates = templates.filter(t => t.is_active);

  // Load dashboard data when counsellor selected
  useEffect(() => {
    if (selectedCounsellorId) {
      loadDashboard();
    } else {
      setConsultationTypes([]);
      setTemplates([]);
    }
  }, [selectedCounsellorId]);

  const loadDashboard = async () => {
    if (!selectedCounsellorId) return;

    setLoading(true);
    setError(null);

    try {
      const token = getAccessToken();
      const [response, counsellor] = await Promise.all([
        getCounsellorDashboard(selectedCounsellorId, token),
        getCounsellor(selectedCounsellorId, token).catch(() => null),
      ]);
      setConsultationTypes(response.consultation_types || []);
      // Deduplicate templates by ID to prevent React key warnings
      const uniqueTemplates = (response.templates || []).filter(
        (template: Template, index: number, self: Template[]) =>
          index === self.findIndex((t) => t.id === template.id)
      );
      setTemplates(uniqueTemplates);
      // Counsellor record carries default_template_id (FK column on counsellors table).
      // The legacy `default_template` string field is unrelated.
      setDefaultTemplateId(
        (counsellor && (counsellor as { default_template_id?: string | null }).default_template_id) || null
      );
    } catch (err) {
      const errorMessage = handleApiError(err);
      setError(errorMessage);
      console.error('Failed to load dashboard:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSetDefaultTemplate = async (templateId: string | null) => {
    if (!selectedCounsellorId) return;
    setUpdatingDefaultId(templateId ?? '__clear__');
    try {
      const result = await setCounsellorDefaultTemplate(
        selectedCounsellorId,
        templateId,
        getAccessToken()
      );
      // Optimistic update
      setDefaultTemplateId(result.default_template_id ?? null);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to set default template');
    } finally {
      setUpdatingDefaultId(null);
    }
  };

  const handleActivateFromConsultationType = async () => {
    if (!selectedCounsellorId || !selectedConsultationTypeId) return;

    const consultationType = consultationTypes.find(ct => ct.id === selectedConsultationTypeId);
    if (!consultationType) return;

    setActionLoading('activate');

    try {
      await activateFromConsultationType(
        selectedCounsellorId,
        selectedConsultationTypeId,
        `My ${consultationType.type_name} Template`,
        getAccessToken()
      );
      alert(`Created and activated new template for ${consultationType.type_name}`);
      setSelectedConsultationTypeId(null);
      loadDashboard(); // Refresh
    } catch (err) {
      const errorMessage = handleApiError(err);
      alert(`Failed to activate: ${errorMessage}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleCloneTemplate = async () => {
    if (!selectedCounsellorId || !selectedTemplateId) return;

    const template = templates.find(t => t.id === selectedTemplateId);
    if (!template) return;

    setActionLoading('clone');

    try {
      await cloneTemplate(
        selectedCounsellorId,
        selectedTemplateId,
        `Clone of ${template.template_name}`,
        getAccessToken()
      );
      alert(`Cloned template: ${template.template_name}`);
      setSelectedTemplateId(null);
      loadDashboard(); // Refresh
    } catch (err) {
      const errorMessage = handleApiError(err);
      alert(`Failed to clone: ${errorMessage}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleCloneFromViewModal = async () => {
    if (!selectedCounsellorId || !viewingTemplate) return;

    setActionLoading('clone');

    try {
      await cloneTemplate(
        selectedCounsellorId,
        viewingTemplate.id,
        `Clone of ${viewingTemplate.template_name}`,
        getAccessToken()
      );
      alert(`Cloned template: ${viewingTemplate.template_name}`);
      setViewingTemplate(null); // Close the view modal
      loadDashboard(); // Refresh
    } catch (err) {
      const errorMessage = handleApiError(err);
      alert(`Failed to clone: ${errorMessage}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeleteTemplate = async (templateId: string, templateName: string) => {
    if (!confirm(`Are you sure you want to delete "${templateName}"? This cannot be undone.`)) {
      return;
    }

    setActionLoading(`delete-${templateId}`);

    try {
      // Call delete template API
      await deleteTemplate(templateId, getAccessToken());

      alert(`Deleted template: ${templateName}`);
      loadDashboard(); // Refresh
    } catch (err) {
      const errorMessage = handleApiError(err);
      alert(`Failed to delete: ${errorMessage}`);
    } finally {
      setActionLoading(null);
    }
  };

  // Check if a consultation type has already been activated
  const isConsultationTypeActivated = (consultationTypeId: string) => {
    return readyTemplates.some(t => t.consultation_type_id === consultationTypeId);
  };

  // Check if a template has already been cloned
  const isTemplateCloned = (templateId: string) => {
    // A template is considered "cloned" if there's an owned template with same consultation_type
    const template = templates.find(t => t.id === templateId);
    if (!template) return false;
    return readyTemplates.some(t => t.consultation_type_id === template.consultation_type_id);
  };

  const getBadgeColor = (badge: string) => {
    switch (badge) {
      case 'Activate':
        return 'bg-blue-100 text-blue-800';
      case 'Owned':
        return 'bg-green-100 text-green-800';
      case 'Shared':
        return 'bg-purple-100 text-purple-800';
      case 'Global':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2">
          Template Configuration
        </h1>
        <p className="text-gray-300">
          Activate templates from session types or clone existing templates
        </p>
      </div>

      {/* Counsellor Selector */}
      <div className="mb-8 bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <CounsellorSelector
          selectedCounsellorId={selectedCounsellorId}
          onCounsellorSelect={setSelectedCounsellorId}
          className="max-w-md"
        />
      </div>

      {/* Loading State */}
      {loading && (
        <div className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-gray-300 border-t-blue-600"></div>
          <p className="mt-4 text-gray-600">Loading dashboard...</p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-8">
          <p className="text-red-800">{error}</p>
          <button
            onClick={loadDashboard}
            className="mt-2 text-sm text-red-600 hover:text-red-700 underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Action Dropdowns: Activate & Clone */}
      {selectedCounsellorId && !loading && !error && (
        <>
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Create New Template</h2>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* LEFT: Activate from Consultation Type */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Activate from Session Type
                </label>
                <select
                  value={selectedConsultationTypeId || ''}
                  onChange={(e) => setSelectedConsultationTypeId(e.target.value || null)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="">Select session type...</option>
                  {consultationTypes.map((ct) => (
                    <option key={ct.id} value={ct.id}>
                      {isConsultationTypeActivated(ct.id) ? '✓ ' : ''}{ct.type_name} ({ct.type_code})
                    </option>
                  ))}
                </select>
                <button
                  onClick={handleActivateFromConsultationType}
                  disabled={!selectedConsultationTypeId || actionLoading === 'activate'}
                  className="mt-3 w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-sm font-medium transition-colors"
                >
                  {actionLoading === 'activate' ? 'Creating...' : 'Activate'}
                </button>
              </div>

              {/* RIGHT: Clone from Template */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Clone from Template
                </label>
                <select
                  value={selectedTemplateId || ''}
                  onChange={(e) => setSelectedTemplateId(e.target.value || null)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="">Select template...</option>
                  {templates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {isTemplateCloned(template.id) ? '✓ ' : ''}
                      {template.template_name} ({template.consultation_types?.type_name || 'Unknown'})
                    </option>
                  ))}
                </select>
                <button
                  onClick={handleCloneTemplate}
                  disabled={!selectedTemplateId || actionLoading === 'clone'}
                  className="mt-3 w-full px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-sm font-medium transition-colors"
                >
                  {actionLoading === 'clone' ? 'Cloning...' : 'Clone'}
                </button>
              </div>
            </div>
          </div>

          {/* Ready-to-Use Templates Section */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900">
                Ready to Use Templates
              </h2>
              <span className="text-sm text-gray-500">
                {readyTemplates.length} active
              </span>
            </div>
            <p className="text-sm text-gray-600 mb-4">
              These templates are configured and ready for use in VSR Screen
            </p>

            {readyTemplates.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                <svg className="w-16 h-16 mx-auto mb-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="font-medium">No Ready Templates</p>
                <p className="text-sm mt-1">Activate or clone a template to get started</p>
              </div>
            ) : (
              <div className="divide-y divide-gray-200">
                {readyTemplates.map((template) => (
                  <div key={template.id} className="py-4 first:pt-0 last:pb-0">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-semibold text-gray-900">
                            {template.template_name || template.template_code}
                          </h3>
                          <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">
                            Active
                          </span>
                          <span className={`text-xs px-2 py-0.5 rounded ${
                            template.access_type === 'owner'
                              ? 'bg-blue-100 text-blue-700'
                              : template.access_type === 'shared'
                              ? 'bg-purple-100 text-purple-700'
                              : 'bg-gray-100 text-gray-700'
                          }`}>
                            {template.access_type === 'owner'
                              ? 'Owned'
                              : template.access_type === 'shared'
                              ? 'Shared by Admin'
                              : 'Common'}
                          </span>
                        </div>
                        <p className="text-sm text-gray-600 mb-1">
                          {template.consultation_types?.type_name || 'Unknown Type'}
                        </p>
                        <p className="text-xs text-gray-500">
                          {template.template_code}
                        </p>
                      </div>

                      <div className="flex items-center gap-2 ml-4">
                        {/* Default-template affordance: show "Default" badge with × clear,
                            or "Make Default" button. Disabled while any update is in flight. */}
                        {defaultTemplateId === template.id ? (
                          <div className="flex items-center gap-1">
                            <span className="text-xs bg-amber-100 text-amber-800 px-2 py-1 rounded font-medium">
                              Default
                            </span>
                            <button
                              onClick={() => handleSetDefaultTemplate(null)}
                              disabled={updatingDefaultId !== null}
                              title="Clear default"
                              className="p-1 text-gray-400 hover:text-red-500 disabled:opacity-50 transition-colors"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => handleSetDefaultTemplate(template.id)}
                            disabled={updatingDefaultId !== null}
                            className="px-2 py-1 text-xs bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-200 rounded font-medium disabled:opacity-50 transition-colors"
                          >
                            {updatingDefaultId === template.id ? 'Setting…' : 'Make Default'}
                          </button>
                        )}
                        {/* Show View Details for common/global templates, Configure for owned/shared */}
                        {template.access_type === 'common' ? (
                          <button
                            onClick={() => setViewingTemplate(template)}
                            className="px-3 py-1.5 bg-gray-600 text-white rounded-lg hover:bg-gray-700 text-sm font-medium transition-colors"
                          >
                            View Details
                          </button>
                        ) : (
                          <button
                            onClick={() => setConfiguringTemplate(template)}
                            className="px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium transition-colors"
                          >
                            Configure Segments
                          </button>
                        )}
                        {template.access_type === 'owner' && (
                          <button
                            onClick={() => handleDeleteTemplate(template.id, template.template_name)}
                            disabled={actionLoading === `delete-${template.id}`}
                            className="px-3 py-1.5 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-sm font-medium transition-colors"
                          >
                            {actionLoading === `delete-${template.id}` ? 'Deleting...' : 'Delete'}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {/* Instructions */}
      {selectedCounsellorId && !loading && (
        <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-6">
          <h3 className="font-semibold text-blue-900 mb-2">Quick Guide</h3>
          <ul className="text-sm text-blue-800 space-y-1.5">
            <li>
              <strong>Activate:</strong> Create a new template from a session type (includes all default segments)
            </li>
            <li>
              <strong>Clone:</strong> Create a customizable copy of any accessible template
            </li>
            <li>
              <strong>✓ Checkmark:</strong> Indicates you already have an active template for that type
            </li>
            <li>
              <strong>Configure Segments:</strong> Customize segments, order, and settings for your owned or shared templates
            </li>
            <li>
              <strong>View Details:</strong> View segment configurations for global templates (read-only). Click "Clone to Customize" to create an editable copy.
            </li>
            <li>
              <strong>Common Templates:</strong> Global templates created by admin (gray badge) are available to all counsellors. You can view and clone them, but cannot configure or delete them.
            </li>
            <li>
              <strong>Owned Templates:</strong> Templates you created (blue badge) can be configured and deleted
            </li>
            <li>
              <strong>Shared Templates:</strong> Templates shared by admin (purple badge) can be viewed or configured depending on your access level ('view' or 'use')
            </li>
          </ul>
        </div>
      )}

      {/* Configure Template Segments Modal */}
      {configuringTemplate && selectedCounsellorId && (
        <TemplateSegmentConfigPanel
          template={configuringTemplate}
          doctorId={selectedCounsellorId}
          onClose={() => {
            setConfiguringTemplate(null);
            loadDashboard(); // Refresh to get latest changes
          }}
        />
      )}

      {/* View Template Details Modal (Read-Only) */}
      {viewingTemplate && (
        <ViewTemplateDetailsModal
          template={viewingTemplate}
          onClose={() => setViewingTemplate(null)}
          onClone={handleCloneFromViewModal}
        />
      )}
    </div>
  );
}
