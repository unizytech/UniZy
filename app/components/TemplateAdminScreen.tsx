'use client';

/**
 * Template Admin Screen
 *
 * PURPOSE:
 * 1. PRIMARY: Manage global templates (counsellor_id = NULL)
 *    - Create starter templates available to all counsellors
 *    - Set default segment configurations for each consultation type
 *
 * 2. SECONDARY: Admin oversight of counsellor templates
 *    - View all counsellor-specific templates
 *    - Edit counsellor templates when needed (admin override)
 *
 * 3. Manage consultation types and segments
 *    - Define consultation types (OP, DISCHARGE, etc.)
 *    - Create/edit segment definitions (building blocks)
 *    - Approve counsellor-requested segments
 *
 * ARCHITECTURE NOTE:
 * - Counsellors create their own templates from CounsellorTemplateConfigScreen
 * - Counsellors can use global templates as starting points
 * - Templates are owned by counsellors (templates.counsellor_id)
 * - No more "activation" concept - templates are directly owned
 */

import React, { useState, useEffect } from 'react';
import type { ConsultationTypeCode, Template } from '@lib/types';
import { useAuth } from '@lib/auth';
import {
  getConsultationTypes,
  getTemplates,
  getAllTemplates,
  deleteTemplate,
  deleteSegment,
  deleteConsultationType,
  reactivateTemplate,
  reactivateSegment,
  reactivateConsultationType,
  getAllSegments,
  getPendingSegments,
  getTemplatePromptPreview,
  handleApiError,
} from '@lib/summaryApi';
import { authGet, authPatch } from '@lib/apiClient';
import { TemplateForm } from './TemplateForm';
import { TemplateSegmentConfigPanel } from './TemplateSegmentConfigPanel';
import { ConsultationTypeSegmentConfigPanel } from './ConsultationTypeSegmentConfigPanel';
import { SegmentForm } from './SegmentForm';
import { SegmentConfigForm } from './SegmentConfigForm';
import { ConsultationTypeForm } from './ConsultationTypeForm';
import { SegmentComparisonsPanel } from './SegmentComparisonsPanel';
import { BulkClonePanel } from './BulkClonePanel';
import { ShareTemplateModal } from './ShareTemplateModal';
import { EditConsultationTypeVisibilityModal } from './EditConsultationTypeVisibilityModal';
import { SegmentAssignmentModal } from './SegmentAssignmentModal';
import { HardDeleteTab } from './HardDeleteTab';
import { TemplateEhrConfigModal } from './TemplateEhrConfigModal';
import { PlanLibraryModal } from './radiology/PlanLibraryModal';
import { ToxicityLibraryModal } from './radiology/ToxicityLibraryModal';
import { StandardTextsModal } from './radiology/StandardTextsModal';
import { ExaminationFieldsModal } from './radiology/ExaminationFieldsModal';

interface TemplateAdminScreenProps {
  userId?: string;
}

type ViewMode = 'templates' | 'consultation-types' | 'segments' | 'pending-requests' | 'segment-comparisons' | 'bulk-clone' | 'hard-delete';
type TemplateFilter = 'admin' | 'doctor' | 'all';

export function TemplateAdminScreen({ userId }: TemplateAdminScreenProps) {
  const { getAccessToken } = useAuth();
  // Get auth token to use as dependency - triggers re-fetch when token becomes available
  const authToken = getAccessToken();
  const [viewMode, setViewMode] = useState<ViewMode>('templates');
  const [consultationTypes, setConsultationTypes] = useState<any[]>([]);
  const [selectedConsultationType, setSelectedConsultationType] = useState<ConsultationTypeCode | 'ALL'>('ALL');
  const [templates, setTemplates] = useState<Template[]>([]);
  const [segments, setSegments] = useState<any[]>([]);
  const [pendingSegments, setPendingSegments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [templateFilter, setTemplateFilter] = useState<TemplateFilter>('all');

  // Modal states
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showCreateSegmentForm, setShowCreateSegmentForm] = useState(false);
  const [showCreateConsultationTypeForm, setShowCreateConsultationTypeForm] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<Template | null>(null);
  const [editingSegment, setEditingSegment] = useState<any | null>(null);
  const [configuringSegment, setConfiguringSegment] = useState<any | null>(null);
  const [configuringTemplate, setConfiguringTemplate] = useState<Template | null>(null);
  const [configuringConsultationType, setConfiguringConsultationType] = useState<{
    code: ConsultationTypeCode;
    name: string;
  } | null>(null);
  const [sharingTemplate, setSharingTemplate] = useState<Template | null>(null);
  const [editingVisibilityConsultationType, setEditingVisibilityConsultationType] = useState<any | null>(null);
  const [viewingAssignmentsSegment, setViewingAssignmentsSegment] = useState<any | null>(null);
  const [showAssociatedTemplates, setShowAssociatedTemplates] = useState(false);
  const [configuringEhrTemplate, setConfiguringEhrTemplate] = useState<Template | null>(null);
  const [planLibraryTemplate, setPlanLibraryTemplate] = useState<Template | null>(null);
  const [toxicityLibraryTemplate, setToxicityLibraryTemplate] = useState<Template | null>(null);
  const [standardTextsTemplate, setStandardTextsTemplate] = useState<Template | null>(null);
  const [examinationFieldsTemplate, setExaminationFieldsTemplate] = useState<Template | null>(null);
  const [associatedTemplatesForType, setAssociatedTemplatesForType] = useState<any>(null);
  const [associatedTemplatesList, setAssociatedTemplatesList] = useState<Template[]>([]);
  const [loadingAssociatedTemplates, setLoadingAssociatedTemplates] = useState(false);
  const [previewingTemplate, setPreviewingTemplate] = useState<{
    template_code: string;
    template_name: string;
    assembled_full_prompt: string | null;
    prompt_assembled_at: string | null;
    has_prompt: boolean;
  } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Filter state for segments
  const [segmentFilter, setSegmentFilter] = useState<'all' | 'core' | 'additional' | 'excluded' | 'inactive'>('all');

  // Search states for each tab
  const [templateSearch, setTemplateSearch] = useState('');
  const [consultationTypeSearch, setConsultationTypeSearch] = useState('');
  const [segmentSearch, setSegmentSearch] = useState('');

  // Highlighted segment state (for navigation from edit modals)
  const [highlightedSegmentId, setHighlightedSegmentId] = useState<string | null>(null);

  // Clear highlight after 15 seconds
  useEffect(() => {
    if (highlightedSegmentId) {
      const timer = setTimeout(() => {
        setHighlightedSegmentId(null);
      }, 15000);
      return () => clearTimeout(timer);
    }
  }, [highlightedSegmentId]);

  // Scroll to highlighted segment (wait for segments to load)
  useEffect(() => {
    if (highlightedSegmentId && viewMode === 'segments' && segments.length > 0) {
      // Add a small delay to ensure DOM is fully rendered
      const timer = setTimeout(() => {
        const element = document.getElementById(`segment-${highlightedSegmentId}`);
        if (element) {
          element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [highlightedSegmentId, viewMode, segments]);

  // Handler for navigating to segment from edit modals
  const handleNavigateToSegmentDefinition = (segmentId: string) => {
    // Close any open modals
    setConfiguringTemplate(null);
    setConfiguringConsultationType(null);

    // Switch to "All Consultation Types" to ensure segment is visible
    setSelectedConsultationType('ALL');

    // Switch to segments tab
    setViewMode('segments');

    // Highlight the segment by ID (unique)
    setHighlightedSegmentId(segmentId);

    // Reset segment filter to 'all' to ensure the segment is visible
    setSegmentFilter('all');
  };

  // Load consultation types on mount or when auth token becomes available
  useEffect(() => {
    if (authToken) {
      loadConsultationTypes();
    }
  }, [authToken]);

  // Load templates when consultation type or filter changes
  useEffect(() => {
    if (selectedConsultationType && authToken) {
      loadTemplates();
    }
  }, [selectedConsultationType, userId, templateFilter, authToken]);

  // Load segments when segments view is active
  useEffect(() => {
    if (viewMode === 'segments' && authToken) {
      loadSegments();
    }
  }, [viewMode, selectedConsultationType, authToken]);

  // Load pending segments when pending-requests view is active
  useEffect(() => {
    if (viewMode === 'pending-requests' && authToken) {
      loadPendingSegments();
    }
  }, [viewMode, authToken]);

  // Reset to first consultation type when switching away from Templates/Segments view with "ALL" selected
  useEffect(() => {
    if (viewMode !== 'segments' && viewMode !== 'templates' && selectedConsultationType === 'ALL' && consultationTypes.length > 0) {
      setSelectedConsultationType(consultationTypes[0].type_code);
    }
  }, [viewMode, selectedConsultationType, consultationTypes]);

  const loadConsultationTypes = async () => {
    try {
      const accessToken = getAccessToken();
      if (!accessToken) {
        console.warn('[TemplateAdminScreen] Auth token not available, skipping consultation types load');
        return;
      }

      const response = await getConsultationTypes(accessToken);
      if (response.success) {
        setConsultationTypes(response.consultation_types);
        if (response.consultation_types.length > 0) {
          setSelectedConsultationType(response.consultation_types[0].type_code);
        }
      }
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const loadTemplates = async () => {
    try {
      setLoading(true);
      setError(null);

      const accessToken = getAccessToken();
      if (!accessToken) {
        console.warn('[TemplateAdminScreen] Auth token not available, skipping template load');
        return;
      }

      let response;
      if (selectedConsultationType === 'ALL') {
        // Fetch all templates across all consultation types
        response = await getAllTemplates(templateFilter, undefined, accessToken);
      } else {
        response = await getTemplates(selectedConsultationType, undefined, templateFilter, accessToken);
      }

      if (response.success) {
        setTemplates(response.templates);
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const loadSegments = async () => {
    try {
      setLoading(true);
      setError(null);

      const accessToken = getAccessToken();
      if (!accessToken) {
        console.warn('[TemplateAdminScreen] Auth token not available, skipping segment load');
        return;
      }

      // Always fetch all segments with full relationship data (consultation_types, templates)
      // Frontend filtering will handle consultation type-specific views
      const response = await getAllSegments(undefined, true, accessToken);

      if (response.success) {
        setSegments(response.segments);
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const loadPendingSegments = async () => {
    try {
      setLoading(true);
      setError(null);

      const accessToken = getAccessToken();
      if (!accessToken) {
        console.warn('[TemplateAdminScreen] Auth token not available, skipping pending segment load');
        return;
      }

      const response = await getPendingSegments(accessToken);

      if (response.success) {
        setPendingSegments(response.segments);
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleToggleTemplate = async (templateCode: string, isActive: boolean) => {
    const action = isActive ? 'inactivate' : 'activate';
    if (!confirm(`Are you sure you want to ${action} template "${templateCode}"?`)) {
      return;
    }

    try {
      setError(null);
      const accessToken = getAccessToken();
      if (isActive) {
        await deleteTemplate(templateCode, accessToken);
      } else {
        await reactivateTemplate(templateCode, accessToken);
      }
      await loadTemplates();
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handleToggleSegment = async (segmentId: string, segmentName: string, isActive: boolean) => {
    try {
      setError(null);
      const accessToken = getAccessToken();
      if (isActive) {
        await deleteSegment(segmentId, accessToken);
      } else {
        await reactivateSegment(segmentId, accessToken);
      }
      await loadSegments();
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handleToggleConsultationType = async (typeCode: string, isActive: boolean) => {
    const action = isActive ? 'inactivate' : 'activate';
    if (!confirm(`Are you sure you want to ${action} session type "${typeCode}"?`)) {
      return;
    }

    try {
      setError(null);
      const accessToken = getAccessToken();
      if (isActive) {
        await deleteConsultationType(typeCode, accessToken);
      } else {
        await reactivateConsultationType(typeCode, accessToken);
      }
      await loadConsultationTypes();
      // Reset to a different consultation type if we inactivated the selected one
      if (isActive && selectedConsultationType === typeCode && consultationTypes.length > 0) {
        setSelectedConsultationType(consultationTypes[0].type_code);
      }
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handleShowAssociatedTemplates = async (consultationType: any) => {
    try {
      setLoadingAssociatedTemplates(true);
      setAssociatedTemplatesForType(consultationType);

      // Fetch templates for this consultation type (using path parameter, not query parameter)
      const response = await authGet(
        `/api/v1/summary/templates/${consultationType.type_code}`,
        getAccessToken()
      );

      if (!response.ok) {
        throw new Error('Failed to fetch associated templates');
      }

      const data = await response.json();
      setAssociatedTemplatesList(data.templates || []);
      setShowAssociatedTemplates(true);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setLoadingAssociatedTemplates(false);
    }
  };

  // Helper function to format visibility status
  const getVisibilityStatus = (consultationType: any) => {
    const hasCounsellorRestrictions = consultationType.visible_to_counsellors && consultationType.visible_to_counsellors.length > 0;
    const hasSchoolRestrictions = consultationType.visible_to_schools && consultationType.visible_to_schools.length > 0;
    const hasSpecializationRestrictions = consultationType.visible_to_specializations && consultationType.visible_to_specializations.length > 0;

    if (!hasCounsellorRestrictions && !hasSchoolRestrictions && !hasSpecializationRestrictions) {
      return { icon: '🌐', text: 'All', color: 'text-green-700 bg-green-100' };
    }

    const restrictions = [];
    if (hasCounsellorRestrictions) restrictions.push(`${consultationType.visible_to_counsellors.length} counsellors`);
    if (hasSchoolRestrictions) restrictions.push(`${consultationType.visible_to_schools.length} schools`);
    if (hasSpecializationRestrictions) restrictions.push(`${consultationType.visible_to_specializations.length} specializations`);

    return {
      icon: '🔒',
      text: restrictions.join(', '),
      color: 'text-orange-700 bg-orange-100'
    };
  };

  // Filter templates based on search query
  const filteredTemplates = templates.filter(template => {
    if (!templateSearch.trim()) return true;
    const searchLower = templateSearch.toLowerCase().trim();
    return (
      template.template_name?.toLowerCase().includes(searchLower) ||
      template.template_code?.toLowerCase().includes(searchLower) ||
      template.description?.toLowerCase().includes(searchLower)
    );
  });

  // Filter consultation types based on search query
  const filteredConsultationTypes = consultationTypes.filter(type => {
    if (!consultationTypeSearch.trim()) return true;
    const searchLower = consultationTypeSearch.toLowerCase().trim();
    return (
      type.type_name?.toLowerCase().includes(searchLower) ||
      type.type_code?.toLowerCase().includes(searchLower) ||
      type.description?.toLowerCase().includes(searchLower) ||
      type.specialty_applicable?.some((spec: string) =>
        spec.toLowerCase().includes(searchLower)
      )
    );
  }).sort((a, b) => (a.type_name || '').localeCompare(b.type_name || ''));

  // Filter segments based on selected filter, consultation type, and search query
  const filteredSegments = segments.filter(seg => {
    // Filter by consultation type (if not "ALL")
    if (selectedConsultationType !== 'ALL') {
      const belongsToConsultationType = seg.consultation_types?.some(
        (ct: any) => ct.type_code === selectedConsultationType
      );
      if (!belongsToConsultationType) return false;
    }

    // Filter by segment category
    if (segmentFilter !== 'all') {
      if (segmentFilter === 'core' && seg.default_category !== 'core') return false;
      if (segmentFilter === 'additional' && seg.default_category !== 'additional') return false;
      if (segmentFilter === 'excluded' && seg.default_category !== 'excluded') return false;
      if (segmentFilter === 'inactive' && seg.is_active !== false) return false;
    }

    // Filter by search query
    if (segmentSearch.trim()) {
      const searchLower = segmentSearch.toLowerCase().trim();
      return (
        seg.segment_name?.toLowerCase().includes(searchLower) ||
        seg.segment_code?.toLowerCase().includes(searchLower) ||
        seg.prompt_section_text?.toLowerCase().includes(searchLower)
      );
    }

    return true;
  }).sort((a, b) => (a.segment_name || '').localeCompare(b.segment_name || ''));

  const handleCreateSuccess = () => {
    setShowCreateForm(false);
    loadTemplates();
  };

  const handleEditSuccess = () => {
    setEditingTemplate(null);
    loadTemplates();
  };

  const handleCreateConsultationTypeSuccess = async () => {
    setShowCreateConsultationTypeForm(false);
    await loadConsultationTypes();
  };

  const handleConfigureSegments = (template: Template) => {
    setConfiguringTemplate(template);
  };

  const handlePreviewPrompt = async (templateCode: string) => {
    setPreviewLoading(true);
    try {
      const token = getAccessToken();
      const data = await getTemplatePromptPreview(templateCode, token);
      setPreviewingTemplate(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load prompt preview');
    } finally {
      setPreviewLoading(false);
    }
  };

  if (loading && templates.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading templates...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Configuration</h1>
            <p className="text-sm text-gray-600 mt-1">
              {viewMode === 'templates'
                ? 'Configure templates from basic segments or inherit from session types'
                : viewMode === 'consultation-types'
                ? 'Configure base segment definitions for session types'
                : 'View and manage all segment definitions'}
            </p>
          </div>
          {viewMode === 'templates' && (
            <button
              onClick={() => {
                console.log('[TEMPLATE_ADMIN] Create Template clicked, selectedConsultationType:', selectedConsultationType);
                setShowCreateForm(true);
              }}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
            >
              + Create Template
            </button>
          )}
          {viewMode === 'consultation-types' && (
            <button
              onClick={() => setShowCreateConsultationTypeForm(true)}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
            >
              + Create New
            </button>
          )}
          {viewMode === 'segments' && (
            <button
              onClick={() => setShowCreateSegmentForm(true)}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
            >
              + Create Segment
            </button>
          )}
        </div>
      </div>

      {/* View Mode Switcher */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <div className="flex gap-2">
          <button
            onClick={() => setViewMode('templates')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'templates'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            📋 Templates
          </button>
          <button
            onClick={() => setViewMode('consultation-types')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'consultation-types'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            🏥 Session Types
          </button>
          <button
            onClick={() => setViewMode('segments')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'segments'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            🧩 Segments
          </button>
          <button
            onClick={() => setViewMode('bulk-clone')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'bulk-clone'
                ? 'bg-green-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            📋 Bulk Clone
          </button>
          <button
            onClick={() => setViewMode('pending-requests')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors relative ${
              viewMode === 'pending-requests'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            🔔 Pending Requests
            {pendingSegments.length > 0 && viewMode !== 'pending-requests' && (
              <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs font-bold rounded-full h-5 w-5 flex items-center justify-center">
                {pendingSegments.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setViewMode('segment-comparisons')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'segment-comparisons'
                ? 'bg-purple-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            🔄 Segment Comparisons
          </button>
          <button
            onClick={() => setViewMode('hard-delete')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'hard-delete'
                ? 'bg-red-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            🗑️ Hard Delete
          </button>
        </div>
      </div>

      {/* Consultation Type Selector - Hide in consultation-types and hard-delete views */}
      {viewMode !== 'consultation-types' && viewMode !== 'hard-delete' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Session Type
          </label>
          <div className="flex flex-wrap gap-2">
            {/* Show "All" button in Templates and Segments views */}
            {(viewMode === 'templates' || viewMode === 'segments') && (
              <button
                onClick={() => {
                  console.log('[TEMPLATE_ADMIN] ALL consultation types button clicked');
                  setSelectedConsultationType('ALL');
                }}
                className={`px-4 py-3 rounded-lg font-medium transition-colors text-sm min-w-[140px] ${
                  selectedConsultationType === 'ALL'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                All Session Types
              </button>
            )}
            {[...consultationTypes].sort((a, b) => (a.type_name || '').localeCompare(b.type_name || '')).map((type) => (
              <button
                key={type.type_code}
                onClick={() => {
                  console.log('[TEMPLATE_ADMIN] Consultation type tab clicked:', type.type_code);
                  setSelectedConsultationType(type.type_code);
                }}
                className={`px-4 py-3 rounded-lg font-medium transition-colors text-[11px] sm:text-xs whitespace-normal text-center leading-snug min-h-[56px] min-w-[100px] max-w-[140px] flex items-center justify-center ${
                  selectedConsultationType === type.type_code
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {type.type_name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-center">
            <svg
              className="w-5 h-5 text-red-600 mr-2"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                clipRule="evenodd"
              />
            </svg>
            <p className="text-red-800">{error}</p>
          </div>
        </div>
      )}

      {/* Templates View */}
      {viewMode === 'templates' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-200">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">
                {selectedConsultationType === 'ALL' ? 'All' : selectedConsultationType} Templates ({filteredTemplates.length} of {templates.length})
              </h2>

              {/* Template Filter */}
              <div className="flex items-center gap-2">
                <div className="flex flex-col gap-2">
                  <label className="text-sm font-medium text-gray-700">Template Type:</label>
                  <div className="text-xs text-gray-500 -mt-1">
                    Global: Shared starter templates • Counsellor: Counsellor-specific templates
                  </div>
                </div>
                <div className="flex gap-1 bg-gray-100 p-1 rounded-lg">
                  <button
                    onClick={() => setTemplateFilter('admin')}
                    className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                      templateFilter === 'admin'
                        ? 'bg-white text-blue-600 shadow-sm'
                        : 'text-gray-600 hover:text-gray-900'
                    }`}
                    title="Global templates available to all counsellors as starter templates"
                  >
                    🌐 Global
                  </button>
                  <button
                    onClick={() => setTemplateFilter('doctor')}
                    className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                      templateFilter === 'doctor'
                        ? 'bg-white text-blue-600 shadow-sm'
                        : 'text-gray-600 hover:text-gray-900'
                    }`}
                    title="Counsellor-owned templates (for admin oversight)"
                  >
                    👤 Counsellor-Owned
                  </button>
                  <button
                    onClick={() => setTemplateFilter('all')}
                    className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                      templateFilter === 'all'
                        ? 'bg-white text-blue-600 shadow-sm'
                        : 'text-gray-600 hover:text-gray-900'
                    }`}
                    title="All templates (global + counsellor-owned)"
                  >
                    All
                  </button>
                </div>
              </div>
            </div>

            {/* Search Input */}
            <div className="relative">
              <input
                type="text"
                value={templateSearch}
                onChange={(e) => setTemplateSearch(e.target.value)}
                placeholder="Search templates by name, code, or description..."
                className="w-full px-4 py-2 pl-10 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <svg
                className="absolute left-3 top-2.5 w-5 h-5 text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              {templateSearch && (
                <button
                  onClick={() => setTemplateSearch('')}
                  className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
                  title="Clear search"
                >
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              )}
            </div>
          </div>

        {filteredTemplates.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            {templateSearch ? (
              <>
                <p className="mb-2">No templates match "{templateSearch}"</p>
                <button
                  onClick={() => setTemplateSearch('')}
                  className="text-blue-600 hover:text-blue-700 font-medium"
                >
                  Clear search
                </button>
              </>
            ) : selectedConsultationType === 'ALL' ? (
              <p className="mb-2">No templates found across all session types</p>
            ) : (
              <>
                <p className="mb-2">No templates found for {selectedConsultationType}</p>
                <button
                  onClick={() => {
                    console.log('[TEMPLATE_ADMIN] Create Template (empty state) clicked, selectedConsultationType:', selectedConsultationType);
                    setShowCreateForm(true);
                  }}
                  className="text-blue-600 hover:text-blue-700 font-medium"
                >
                  Create your first template
                </button>
              </>
            )}
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {filteredTemplates.map((template, index) => (
              <div
                key={`${template.id}-${template.counsellor_id || 'admin'}-${index}`}
                className="p-4 hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-lg font-semibold text-gray-900">
                        {template.template_name}
                      </h3>
                      <span className="text-xs bg-gray-200 text-gray-700 px-2 py-0.5 rounded">
                        {template.template_code}
                      </span>
                      {!template.counsellor_id ? (
                        <span className="text-xs font-medium text-blue-600">
                          Common Template
                        </span>
                      ) : (
                        <span className="text-xs font-medium text-green-600">
                          Owned Template
                        </span>
                      )}
                      {!template.is_active && (
                        <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">
                          Inactive
                        </span>
                      )}
                      {selectedConsultationType === 'ALL' && template.consultation_type_code && (
                        <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded">
                          {template.consultation_type_code}
                        </span>
                      )}
                    </div>

                    <p className="text-sm text-gray-600 mt-1">
                      {template.description}
                    </p>

                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                      {template.specialization && (
                        <span className="flex items-center gap-1">
                          <span className="font-medium">Specialization:</span>
                          {template.specialization}
                        </span>
                      )}
                      {template.estimated_extraction_time_seconds && (
                        <span className="flex items-center gap-1">
                          <span className="font-medium">Est. Time:</span>
                          {template.estimated_extraction_time_seconds}s
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 ml-4">
                    <button
                      onClick={() => handleConfigureSegments(template)}
                      className="bg-green-600 hover:bg-green-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                    >
                      Configure Segments
                    </button>
                    <button
                      onClick={() => handlePreviewPrompt(template.template_code)}
                      className="bg-cyan-600 hover:bg-cyan-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Preview assembled prompt"
                      disabled={previewLoading}
                    >
                      {previewLoading ? '...' : 'Preview'}
                    </button>
                    <button
                      onClick={() => setSharingTemplate(template)}
                      className="bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                      title="Share template with counsellors"
                    >
                      Share
                    </button>
                    <button
                      onClick={() => setConfiguringEhrTemplate(template)}
                      className="bg-orange-600 hover:bg-orange-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                      title="Configure EHR URL suffix for this template"
                    >
                      EHR
                    </button>
                    {template.template_code?.startsWith('RS_') && (
                      <>
                        <button
                          onClick={() => setPlanLibraryTemplate(template)}
                          className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                          title="Edit per-template plan library"
                        >
                          Plan Library
                        </button>
                        <button
                          onClick={() => setToxicityLibraryTemplate(template)}
                          className="bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                          title="Edit per-template toxicity library"
                        >
                          Toxicity Library
                        </button>
                        <button
                          onClick={() => setStandardTextsTemplate(template)}
                          className="bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                          title="Edit per-template standard text blocks"
                        >
                          Standard Texts
                        </button>
                        <button
                          onClick={() => setExaminationFieldsTemplate(template)}
                          className="bg-slate-700 hover:bg-slate-800 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                          title="View site-specific examination fields"
                        >
                          Examination
                        </button>
                      </>
                    )}
                    <button
                      onClick={() => setEditingTemplate(template)}
                      className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleToggleTemplate(template.template_code, template.is_active !== false)}
                      className={`${template.is_active === false ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700'} text-white px-3 py-1.5 rounded text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed`}
                      title={template.is_active === false ? 'Activate template' : 'Inactivate template'}
                    >
                      {template.is_active === false ? 'Activate' : 'Inactivate'}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
        </div>
      )}

      {/* Consultation Types View */}
      {viewMode === 'consultation-types' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900 mb-2">
              Session Types ({filteredConsultationTypes.length} of {consultationTypes.length})
            </h2>
            <p className="text-sm text-gray-600 mb-4">
              Configure base segment definitions that templates inherit from
            </p>

            {/* Search Input */}
            <div className="relative">
              <input
                type="text"
                value={consultationTypeSearch}
                onChange={(e) => setConsultationTypeSearch(e.target.value)}
                placeholder="Search by name, code, description, or specialty..."
                className="w-full px-4 py-2 pl-10 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <svg
                className="absolute left-3 top-2.5 w-5 h-5 text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              {consultationTypeSearch && (
                <button
                  onClick={() => setConsultationTypeSearch('')}
                  className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
                  title="Clear search"
                >
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              )}
            </div>
          </div>

          {filteredConsultationTypes.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <p className="mb-2">No session types match "{consultationTypeSearch}"</p>
              <button
                onClick={() => setConsultationTypeSearch('')}
                className="text-blue-600 hover:text-blue-700 font-medium"
              >
                Clear search
              </button>
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {filteredConsultationTypes.map((type) => (
              <div
                key={type.id}
                className="p-4 hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-lg font-semibold text-gray-900">
                        {type.type_name}
                      </h3>
                      <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded font-mono">
                        {type.type_code}
                      </span>
                      {type.is_active && (
                        <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">
                          Active
                        </span>
                      )}
                    </div>

                    <p className="text-sm text-gray-600 mt-1">
                      {type.description}
                    </p>

                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                      {type.specialty_applicable && type.specialty_applicable.length > 0 && (
                        <span className="flex items-center gap-1">
                          <span className="font-medium">Specialties:</span>
                          {type.specialty_applicable.join(', ')}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 ml-4 flex-wrap">
                    {/* Emotion Analysis Configuration - Stacked vertically */}
                    <div className="flex flex-col gap-1 text-xs min-w-[180px]">
                      {/* Emotion Analysis Checkbox - Works with or without transcript (audio-only mode) */}
                      <div className="flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          id={`emotion-${type.type_code}`}
                          checked={type.enable_emotion_analysis ?? false}
                          onChange={async (e) => {
                            const enable = e.target.checked;
                            try {
                              const response = await authPatch(
                                `/api/v1/summary/admin/consultation-types/${type.type_code}/emotion-analysis?enable=${enable}`,
                                getAccessToken(),
                                {}
                              );
                              if (!response.ok) throw new Error('Failed to update emotion analysis');

                              // Update local state
                              setConsultationTypes(prevTypes =>
                                prevTypes.map(t =>
                                  t.type_code === type.type_code
                                    ? { ...t, enable_emotion_analysis: enable }
                                    : t
                                )
                              );
                            } catch (error) {
                              console.error('Error updating emotion analysis:', error);
                              setError('Failed to update emotion analysis');
                            }
                          }}
                          className="h-3.5 w-3.5 rounded border-gray-300 focus:ring-blue-500 text-blue-600"
                        />
                        <label
                          htmlFor={`emotion-${type.type_code}`}
                          className="font-medium cursor-pointer text-gray-700"
                          title={type.skip_transcription === true
                            ? "Uses audio-only emotion analysis (no transcript required)"
                            : "Combined text+audio emotion analysis"
                          }
                        >
                          Emotion{type.skip_transcription === true && <span className="text-orange-500 ml-1">(audio)</span>}
                        </label>
                      </div>

                      {/* Triage Analysis Checkbox - Works with or without transcript (uses extraction JSON) */}
                      <div className="flex items-center gap-1.5 mt-1">
                        <input
                          type="checkbox"
                          id={`triage-${type.type_code}`}
                          checked={type.enable_triage_analysis !== false}
                          onChange={async (e) => {
                            const enable = e.target.checked;
                            try {
                              const response = await authPatch(
                                `/api/v1/summary/admin/consultation-types/${type.type_code}/triage-analysis?enable=${enable}`,
                                getAccessToken(),
                                {}
                              );
                              if (!response.ok) throw new Error('Failed to update triage analysis');

                              // Update local state
                              setConsultationTypes(prevTypes =>
                                prevTypes.map(t =>
                                  t.type_code === type.type_code
                                    ? { ...t, enable_triage_analysis: enable }
                                    : t
                                )
                              );
                            } catch (error) {
                              console.error('Error updating triage analysis:', error);
                              setError('Failed to update triage analysis');
                            }
                          }}
                          className="w-3.5 h-3.5 bg-white border-gray-300 rounded focus:ring-blue-500 text-blue-600"
                        />
                        <label
                          htmlFor={`triage-${type.type_code}`}
                          className="cursor-pointer text-gray-700"
                          title="Enable/disable triage suggestions (red flags, missing investigations). Works without transcript."
                        >
                          Triage
                        </label>
                      </div>

                      {/* Insights & Interventions Checkbox - Requires transcript */}
                      <div className="flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          id={`insights-${type.type_code}`}
                          checked={type.enable_consultation_insights !== false}
                          disabled={type.skip_transcription === true}
                          onChange={async (e) => {
                            const enable = e.target.checked;
                            try {
                              const response = await authPatch(
                                `/api/v1/summary/admin/consultation-types/${type.type_code}/consultation-insights?enable=${enable}`,
                                getAccessToken(),
                                {}
                              );
                              if (!response.ok) throw new Error('Failed to update session insights');

                              // Update local state
                              setConsultationTypes(prevTypes =>
                                prevTypes.map(t =>
                                  t.type_code === type.type_code
                                    ? { ...t, enable_consultation_insights: enable }
                                    : t
                                )
                              );
                            } catch (error) {
                              console.error('Error updating consultation insights:', error);
                              setError('Failed to update session insights');
                            }
                          }}
                          className={`w-3.5 h-3.5 bg-white border-gray-300 rounded focus:ring-blue-500 ${
                            type.skip_transcription === true ? 'text-gray-400 cursor-not-allowed' : 'text-blue-600'
                          }`}
                        />
                        <label
                          htmlFor={`insights-${type.type_code}`}
                          className={`cursor-pointer ${type.skip_transcription === true ? 'text-gray-400' : 'text-gray-700'}`}
                          title={type.skip_transcription === true
                            ? "Requires transcript - disabled in No Transcript mode"
                            : "Enable/disable session insights, assessments, and interventions"
                          }
                        >
                          Insights{type.skip_transcription === true && <span className="text-red-400 ml-1">(requires transcript)</span>}
                        </label>
                      </div>

                      {/* No Transcript (Direct Audio Extraction) Checkbox */}
                      <div className="flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          id={`no-transcript-${type.type_code}`}
                          checked={type.skip_transcription === true}
                          onChange={async (e) => {
                            const enable = e.target.checked;
                            try {
                              const response = await authPatch(
                                `/api/v1/summary/admin/consultation-types/${type.type_code}/skip-transcription?enable=${enable}`,
                                getAccessToken(),
                                {}
                              );
                              if (!response.ok) throw new Error('Failed to update skip transcription');

                              // Update local state - when enabling, only disable consultation_insights (requires transcript)
                              // Emotion uses audio-only mode and Triage uses extraction JSON (both work without transcript)
                              setConsultationTypes(prevTypes =>
                                prevTypes.map(t =>
                                  t.type_code === type.type_code
                                    ? {
                                        ...t,
                                        skip_transcription: enable,
                                        ...(enable && {
                                          enable_consultation_insights: false,
                                        }),
                                      }
                                    : t
                                )
                              );
                            } catch (error) {
                              console.error('Error updating skip transcription:', error);
                              setError('Failed to update no transcript setting');
                            }
                          }}
                          className="w-3.5 h-3.5 text-orange-600 bg-white border-gray-300 rounded focus:ring-orange-500"
                        />
                        <label
                          htmlFor={`no-transcript-${type.type_code}`}
                          className="text-gray-700 cursor-pointer"
                          title="Skip transcription and extract insights directly from audio. Emotion uses audio-only mode, Triage runs normally. Only Session Insights is disabled (requires transcript)."
                        >
                          No Transcript
                        </label>
                      </div>
                    </div>

                    <button
                      onClick={() =>
                        setConfiguringConsultationType({
                          code: type.type_code,
                          name: type.type_name,
                        })
                      }
                      className="bg-green-600 hover:bg-green-700 text-white px-2 py-1 rounded text-xs font-medium transition-colors"
                    >
                      Configure Segments
                    </button>
                    <button
                      onClick={() => setEditingVisibilityConsultationType(type)}
                      className="bg-blue-600 hover:bg-blue-700 text-white px-2 py-1 rounded text-xs font-medium transition-colors"
                      title="Edit visibility settings"
                    >
                      Visibility
                    </button>
                    <button
                      onClick={() => handleShowAssociatedTemplates(type)}
                      disabled={loadingAssociatedTemplates}
                      className="bg-purple-600 hover:bg-purple-700 text-white px-2 py-1 rounded text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      title="View templates using this session type"
                    >
                      {loadingAssociatedTemplates ? 'Loading...' : 'Assc. Templates'}
                    </button>
                    <button
                      onClick={() => handleToggleConsultationType(type.type_code, type.is_active !== false)}
                      className={`${type.is_active === false ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700'} text-white px-2 py-1 rounded text-xs font-medium transition-colors`}
                      title={type.is_active === false ? 'Activate this session type' : 'Inactivate this session type'}
                    >
                      {type.is_active === false ? 'Activate' : 'Inactivate'}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
          )}
        </div>
      )}

      {/* Segments View */}
      {viewMode === 'segments' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-200">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  All Segments ({filteredSegments.length} of {segments.length})
                </h2>
                <p className="text-sm text-gray-600 mt-1">
                  View and manage segment definitions {selectedConsultationType === 'ALL' ? 'across all session types' : `for ${selectedConsultationType}`}
                </p>
              </div>

              {/* Filter Dropdown and Refresh Button */}
              <div className="flex items-center gap-2">
                <label className="text-sm font-medium text-gray-700">Filter:</label>
                <select
                  value={segmentFilter}
                  onChange={(e) => setSegmentFilter(e.target.value as any)}
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="all">All Segments</option>
                  <option value="core">Core</option>
                  <option value="additional">Additional</option>
                  <option value="excluded">Excluded</option>
                  <option value="inactive">Inactive</option>
                </select>
                <button
                  onClick={loadSegments}
                  disabled={loading}
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 bg-white hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  title="Refresh segments"
                >
                  <svg
                    className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                    />
                  </svg>
                  <span>Refresh</span>
                </button>
              </div>
            </div>

            {/* Search Input */}
            <div className="relative">
              <input
                type="text"
                value={segmentSearch}
                onChange={(e) => setSegmentSearch(e.target.value)}
                placeholder="Search segments by name, code, or description..."
                className="w-full px-4 py-2 pl-10 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <svg
                className="absolute left-3 top-2.5 w-5 h-5 text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              {segmentSearch && (
                <button
                  onClick={() => setSegmentSearch('')}
                  className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
                  title="Clear search"
                >
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              )}
            </div>
          </div>

          {filteredSegments.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              {segmentSearch ? (
                <>
                  <p className="mb-2">No segments match "{segmentSearch}"</p>
                  <button
                    onClick={() => setSegmentSearch('')}
                    className="text-blue-600 hover:text-blue-700 font-medium"
                  >
                    Clear search
                  </button>
                </>
              ) : (
                <>
                  <p className="mb-2">No segments found</p>
                  <button
                    onClick={() => setShowCreateSegmentForm(true)}
                    className="text-blue-600 hover:text-blue-700 font-medium"
                  >
                    Create your first segment
                  </button>
                </>
              )}
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {filteredSegments.map((segment) => (
                <div
                  key={segment.id}
                  id={`segment-${segment.id}`}
                  className={`p-4 transition-all duration-300 ${
                    highlightedSegmentId === segment.id
                      ? 'bg-yellow-100 border-2 border-yellow-400 shadow-lg'
                      : 'hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="text-lg font-semibold text-gray-900">
                          {segment.segment_name}
                        </h3>
                        <span className="text-xs bg-gray-200 text-gray-700 px-2 py-0.5 rounded font-mono">
                          {segment.segment_code}
                        </span>
                        {segment.is_required && (
                          <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">
                            Required
                          </span>
                        )}
                        {segment.is_active === false && (
                          <span className="text-xs bg-red-600 text-white px-2 py-0.5 rounded font-semibold">
                            INACTIVE
                          </span>
                        )}
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          segment.default_category === 'core'
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-green-100 text-green-700'
                        }`}>
                          {segment.default_category?.toUpperCase()}
                        </span>
                      </div>

                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                        <button
                          onClick={() => setViewingAssignmentsSegment(segment)}
                          className="flex items-center gap-1 text-blue-600 hover:text-blue-700 font-medium hover:underline"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                          </svg>
                          <span>Assigned to</span>
                          <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded-full text-xs font-medium">
                            {((segment.consultation_types?.length || 0) + (segment.templates?.length || 0)) || 0}
                          </span>
                        </button>
                        <span className="flex items-center gap-1">
                          <span className="font-medium">Brevity:</span>
                          {segment.default_brevity_level || 'balanced'}
                        </span>
                        <span className="flex items-center gap-1">
                          <span className="font-medium">Terminology:</span>
                          {segment.default_terminology_style || 'medical_terms'}
                        </span>
                        <span className="flex items-center gap-1">
                          <span className="font-medium">Order:</span>
                          {segment.display_order}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 ml-4">
                      <button
                        onClick={() => setEditingSegment(segment)}
                        className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                        title="Edit global fields (prompt, schema, name)"
                      >
                        Edit Definition
                      </button>
                      <button
                        onClick={() => setConfiguringSegment(segment)}
                        className="bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                        title="Edit association-specific configuration"
                      >
                        Edit Config
                      </button>
                      <button
                        onClick={() => handleToggleSegment(segment.id, segment.segment_name, segment.is_active !== false)}
                        className={`${segment.is_active === false ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700'} text-white px-3 py-1.5 rounded text-sm font-medium transition-colors`}
                        title={segment.is_active === false ? 'Activate this segment' : 'Inactivate this segment'}
                      >
                        {segment.is_active === false ? 'Activate' : 'Inactivate'}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Pending Requests View */}
      {viewMode === 'pending-requests' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-200 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">
                Pending Segment Requests ({pendingSegments.length})
              </h2>
              <p className="text-sm text-gray-600 mt-1">
                Review and approve counsellor segment requests by adding JSON schema
              </p>
            </div>
            <button
              onClick={loadPendingSegments}
              className="px-3 py-1.5 text-sm font-medium text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
            >
              ↻ Refresh
            </button>
          </div>

          {loading ? (
            <div className="p-8 text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Loading pending requests...</p>
            </div>
          ) : pendingSegments.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <div className="w-16 h-16 mx-auto mb-4 text-gray-400">
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </div>
              <p className="font-medium">No Pending Requests</p>
              <p className="text-sm mt-1">All segment requests have been reviewed</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {pendingSegments.map((segment) => (
                <div
                  key={segment.id}
                  className="p-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="text-lg font-semibold text-gray-900">
                          {segment.segment_name}
                        </h3>
                        <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded font-medium">
                          Pending Review
                        </span>
                        <span className="text-xs bg-gray-200 text-gray-700 px-2 py-0.5 rounded">
                          {segment.segment_code}
                        </span>
                      </div>

                      <p className="text-sm text-gray-600 mt-2">
                        {segment.prompt_section_text}
                      </p>

                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                        <span className="flex items-center gap-1">
                          <span className="font-medium">Requested by:</span>
                          {segment.requester_name || 'Unknown'} ({segment.requester_email || 'N/A'})
                        </span>
                        <span className="flex items-center gap-1">
                          <span className="font-medium">Session Type:</span>
                          {segment.consultation_type_name || segment.consultation_type_code}
                        </span>
                        <span className="flex items-center gap-1">
                          <span className="font-medium">Category:</span>
                          {segment.default_category}
                        </span>
                        <span className="flex items-center gap-1">
                          <span className="font-medium">Brevity:</span>
                          {segment.default_brevity_level}
                        </span>
                      </div>

                      {segment.created_at && (
                        <p className="text-xs text-gray-400 mt-1">
                          Requested on {new Date(segment.created_at).toLocaleDateString()} at{' '}
                          {new Date(segment.created_at).toLocaleTimeString()}
                        </p>
                      )}
                    </div>

                    <div className="flex items-center gap-2 ml-4">
                      <button
                        onClick={() => setEditingSegment(segment)}
                        className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                      >
                        Review & Approve
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Segment Comparisons View */}
      {viewMode === 'segment-comparisons' && userId && selectedConsultationType !== 'ALL' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <SegmentComparisonsPanel
            userId={userId}
            adminId={userId}
            consultationType={selectedConsultationType as ConsultationTypeCode}
          />
        </div>
      )}

      {/* Bulk Clone View */}
      {viewMode === 'bulk-clone' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <BulkClonePanel
            consultationTypes={consultationTypes}
            userId={userId}
            onComplete={() => {
              // Refresh segments list after bulk cloning
              loadSegments();
            }}
          />
        </div>
      )}

      {/* Hard Delete View */}
      {viewMode === 'hard-delete' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <HardDeleteTab />
        </div>
      )}

      {/* Create Template Modal */}
      {showCreateForm && (
        <TemplateForm
          consultationTypeCode={
            selectedConsultationType === 'ALL'
              ? (consultationTypes[0]?.type_code as ConsultationTypeCode) // Default to first CT when ALL is selected
              : (selectedConsultationType as ConsultationTypeCode)
          }
          // Note: Don't pass userId - admin users create global templates with counsellor_id = NULL
          onSuccess={handleCreateSuccess}
          onCancel={() => setShowCreateForm(false)}
        />
      )}

      {/* Edit Template Modal */}
      {editingTemplate && (
        <TemplateForm
          template={editingTemplate}
          consultationTypeCode={
            (editingTemplate.consultation_type_code || selectedConsultationType) as ConsultationTypeCode
          }
          // Note: Don't pass userId - admin users edit global templates, counsellor_id preserved from original
          onSuccess={handleEditSuccess}
          onCancel={() => setEditingTemplate(null)}
        />
      )}

      {/* Configure Template Segments Modal */}
      {configuringTemplate && (
        <TemplateSegmentConfigPanel
          template={configuringTemplate}
          onClose={() => setConfiguringTemplate(null)}
          onNavigateToSegmentDefinition={handleNavigateToSegmentDefinition}
        />
      )}

      {/* Configure Consultation Type Segments Modal */}
      {configuringConsultationType && (
        <ConsultationTypeSegmentConfigPanel
          consultationTypeCode={configuringConsultationType.code}
          consultationTypeName={configuringConsultationType.name}
          onClose={() => setConfiguringConsultationType(null)}
          onNavigateToSegmentDefinition={handleNavigateToSegmentDefinition}
        />
      )}

      {/* Create Segment Modal */}
      {showCreateSegmentForm && selectedConsultationType !== 'ALL' && (
        <SegmentForm
          consultationTypeCode={selectedConsultationType as ConsultationTypeCode}
          adminId={userId}
          consultationTypes={consultationTypes}
          onSuccess={() => {
            setShowCreateSegmentForm(false);
            loadSegments();
          }}
          onCancel={() => setShowCreateSegmentForm(false)}
        />
      )}

      {/* Edit Segment Definition Modal (Global fields only) */}
      {editingSegment && (
        <SegmentForm
          segment={editingSegment}
          consultationTypeCode={
            (editingSegment.consultation_type_code || selectedConsultationType) as ConsultationTypeCode
          }
          adminId={userId}
          consultationTypes={consultationTypes}
          onSuccess={() => {
            setEditingSegment(null);
            // Reload appropriate list based on segment status
            if (editingSegment.status === 'pending_approval') {
              loadPendingSegments();
            } else {
              loadSegments();
            }
          }}
          onCancel={() => setEditingSegment(null)}
        />
      )}

      {/* Edit Segment Configuration Modal (Association-specific) */}
      {configuringSegment && (
        <SegmentConfigForm
          segment={configuringSegment}
          onSuccess={() => {
            setConfiguringSegment(null);
            loadSegments();
          }}
          onCancel={() => setConfiguringSegment(null)}
        />
      )}

      {/* Create Consultation Type Modal */}
      {showCreateConsultationTypeForm && (
        <ConsultationTypeForm
          onSuccess={handleCreateConsultationTypeSuccess}
          onCancel={() => setShowCreateConsultationTypeForm(false)}
        />
      )}

      {/* Share Template Modal */}
      {sharingTemplate && (
        <ShareTemplateModal
          template={sharingTemplate}
          isOpen={!!sharingTemplate}
          onClose={() => setSharingTemplate(null)}
          onShareComplete={() => {
            // Optionally reload templates to refresh shared status
            loadTemplates();
          }}
        />
      )}

      {/* EHR Configuration Modal */}
      {configuringEhrTemplate && (
        <TemplateEhrConfigModal
          template={configuringEhrTemplate}
          onClose={() => setConfiguringEhrTemplate(null)}
        />
      )}

      {/* Radiology config modals (per-template, only opened from RS_* rows) */}
      {planLibraryTemplate && (
        <PlanLibraryModal
          template={planLibraryTemplate}
          onClose={() => setPlanLibraryTemplate(null)}
        />
      )}
      {toxicityLibraryTemplate && (
        <ToxicityLibraryModal
          template={toxicityLibraryTemplate}
          onClose={() => setToxicityLibraryTemplate(null)}
        />
      )}
      {standardTextsTemplate && (
        <StandardTextsModal
          template={standardTextsTemplate}
          onClose={() => setStandardTextsTemplate(null)}
        />
      )}
      {examinationFieldsTemplate && (
        <ExaminationFieldsModal
          template={examinationFieldsTemplate}
          onClose={() => setExaminationFieldsTemplate(null)}
        />
      )}

      {/* Edit Consultation Type Visibility Modal */}
      {editingVisibilityConsultationType && (
        <EditConsultationTypeVisibilityModal
          consultationType={editingVisibilityConsultationType}
          isOpen={!!editingVisibilityConsultationType}
          onClose={() => setEditingVisibilityConsultationType(null)}
          onSaveComplete={() => {
            setEditingVisibilityConsultationType(null);
            loadConsultationTypes();
          }}
        />
      )}

      {/* Segment Assignment Modal */}
      {viewingAssignmentsSegment && (
        <SegmentAssignmentModal
          segment={viewingAssignmentsSegment}
          isOpen={!!viewingAssignmentsSegment}
          onClose={() => setViewingAssignmentsSegment(null)}
          onAssignmentChange={() => {
            // Refresh segments list after assignment
            loadSegments();
          }}
        />
      )}

      {/* Prompt Preview Modal */}
      {previewingTemplate && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="bg-cyan-600 text-white p-6 rounded-t-lg">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-2xl font-bold">{previewingTemplate.template_name}</h2>
                  <p className="text-cyan-100 text-sm mt-1">
                    <span className="font-mono">{previewingTemplate.template_code}</span>
                    {previewingTemplate.prompt_assembled_at && (
                      <span className="ml-3">
                        Assembled: {new Date(previewingTemplate.prompt_assembled_at).toLocaleString()}
                      </span>
                    )}
                  </p>
                </div>
                <button
                  onClick={() => setPreviewingTemplate(null)}
                  className="text-white hover:bg-cyan-700 rounded-lg p-2 transition-colors"
                  title="Close"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="p-6">
              {previewingTemplate.has_prompt ? (
                <pre className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-sm text-gray-800 whitespace-pre-wrap break-words font-mono max-h-[60vh] overflow-y-auto">
                  {previewingTemplate.assembled_full_prompt}
                </pre>
              ) : (
                <div className="text-center py-12">
                  <svg className="w-16 h-16 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <p className="text-gray-600 text-lg font-medium">Not Assembled Yet</p>
                  <p className="text-gray-500 text-sm mt-1">
                    This template does not have an assembled prompt. Use &quot;Reassemble&quot; to generate one.
                  </p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="bg-gray-50 px-6 py-4 rounded-b-lg border-t border-gray-200">
              <button
                onClick={() => setPreviewingTemplate(null)}
                className="w-full px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg font-medium transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Associated Templates Modal */}
      {showAssociatedTemplates && associatedTemplatesForType && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="bg-purple-600 text-white p-6 rounded-t-lg">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-2xl font-bold">Templates - {associatedTemplatesForType.type_name}</h2>
                  <p className="text-purple-100 text-sm mt-1">
                    Templates using {associatedTemplatesForType.type_code} session type
                  </p>
                </div>
                <button
                  onClick={() => {
                    setShowAssociatedTemplates(false);
                    setAssociatedTemplatesForType(null);
                    setAssociatedTemplatesList([]);
                  }}
                  className="text-white hover:bg-purple-700 rounded-lg p-2 transition-colors"
                  title="Close"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="p-6">
              {associatedTemplatesList.length === 0 ? (
                <div className="text-center py-12">
                  <svg className="w-16 h-16 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <p className="text-gray-600 text-lg font-medium">No Templates Found</p>
                  <p className="text-gray-500 text-sm mt-1">
                    No templates are using the {associatedTemplatesForType.type_code} session type yet.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4">
                    <p className="text-sm text-blue-800">
                      <span className="font-semibold">{associatedTemplatesList.length}</span> template{associatedTemplatesList.length !== 1 ? 's' : ''} found
                    </p>
                  </div>

                  {associatedTemplatesList.map((template: Template) => (
                    <div
                      key={template.id}
                      className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <h3 className="font-semibold text-gray-900">{template.template_name}</h3>
                            <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded font-mono">
                              {template.template_code}
                            </span>
                            {template.is_active && (
                              <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">
                                Active
                              </span>
                            )}
                            {template.is_default && (
                              <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
                                Default
                              </span>
                            )}
                          </div>
                          {template.description && (
                            <p className="text-sm text-gray-600 mt-1">{template.description}</p>
                          )}
                          <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                            {template.counsellor_id ? (
                              <span className="flex items-center gap-1">
                                <span className="font-medium">Owner:</span>
                                Counsellor-specific
                              </span>
                            ) : (
                              <span className="flex items-center gap-1">
                                <span className="font-medium">Type:</span>
                                Global Template
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="bg-gray-50 px-6 py-4 rounded-b-lg border-t border-gray-200">
              <button
                onClick={() => {
                  setShowAssociatedTemplates(false);
                  setAssociatedTemplatesForType(null);
                  setAssociatedTemplatesList([]);
                }}
                className="w-full px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg font-medium transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
