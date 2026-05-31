'use client';

import React, { useState, useEffect } from 'react';
import type { ConsultationTypeCode, BrevityLevel, TerminologyStyle } from '@lib/types';
import {
  createSegment,
  updateSegment,
  approveSegmentRequest,
  getConsultationTypes,
  getTemplates,
  getAllSegments,
  cloneSegment,
  combineSegments,
  handleApiError,
  type CreateSegmentRequest,
  type UpdateSegmentRequest,
  type CloneSegmentRequest,
  type CombineSegmentSource,
} from '@lib/summaryApi';
import { useAuth } from '@lib/auth';

interface SegmentFormProps {
  segment?: any; // Existing segment for edit mode
  consultationTypeCode?: ConsultationTypeCode;
  adminId?: string; // Required for approval
  consultationTypes?: any[]; // Pre-loaded consultation types to avoid API call
  onSuccess: () => void;
  onCancel: () => void;
}

export function SegmentForm({
  segment,
  consultationTypeCode: initialConsultationType,
  adminId,
  consultationTypes: preloadedConsultationTypes,
  onSuccess,
  onCancel,
}: SegmentFormProps) {
  const { getAccessToken } = useAuth();
  const isEditMode = !!segment;
  const isPendingApproval = segment?.status === 'pending_approval';

  // Determine initial assignment type from segment data
  const getInitialAssignmentType = () => {
    if (segment?.template_id) return 'template';
    return 'consultation_type';
  };

  const [consultationTypes, setConsultationTypes] = useState<any[]>(preloadedConsultationTypes || []);
  const [availableTemplates, setAvailableTemplates] = useState<any[]>([]);
  const [assignmentType, setAssignmentType] = useState<'consultation_type' | 'template'>(
    isEditMode ? getInitialAssignmentType() : 'consultation_type'
  );

  // Clone functionality
  const [useClone, setUseClone] = useState(false);
  const [availableSegments, setAvailableSegments] = useState<any[]>([]);
  const [selectedParentSegment, setSelectedParentSegment] = useState<string>(''); // segment_code for API
  const [selectedParentSegmentId, setSelectedParentSegmentId] = useState<string>(''); // segment id for UI selection
  const [sourceConsultationTypeId, setSourceConsultationTypeId] = useState<string>('');
  const [sourceConsultationTypeForClone, setSourceConsultationTypeForClone] = useState<string>('');

  // Combine functionality
  const [useCombine, setUseCombine] = useState(false);
  const [selectedSegmentsToCombine, setSelectedSegmentsToCombine] = useState<CombineSegmentSource[]>([]);
  const [combineConsultationTypeId, setCombineConsultationTypeId] = useState<string>('');
  const [combining, setCombining] = useState(false);
  const [mergeNotes, setMergeNotes] = useState<string>('');

  // Get unique consultation types from available segments for clone source selection
  const getUniqueConsultationTypesFromSegments = () => {
    const ctMap = new Map<string, { id: string; code: string; name: string }>();
    availableSegments.forEach(seg => {
      // Check consultation_types array (returned by backend)
      if (seg.consultation_types && Array.isArray(seg.consultation_types)) {
        seg.consultation_types.forEach((ct: any) => {
          if (ct.type_id) {
            ctMap.set(ct.type_id, {
              id: ct.type_id,
              code: ct.type_code,
              name: ct.type_name
            });
          }
        });
      }
    });
    return Array.from(ctMap.values());
  };

  // Filter segments by selected source consultation type
  const getFilteredSegmentsForClone = () => {
    if (!sourceConsultationTypeForClone) return [];
    return availableSegments.filter(seg => {
      // Check consultation_types array (returned by backend)
      if (seg.consultation_types && Array.isArray(seg.consultation_types)) {
        return seg.consultation_types.some((ct: any) =>
          ct.type_id === sourceConsultationTypeForClone
        );
      }
      return false;
    });
  };

  const [formData, setFormData] = useState({
    segment_code: segment?.segment_code || '',
    segment_name: segment?.segment_name || '',
    consultation_type_code: segment?.consultation_type_code || initialConsultationType || 'OP',
    template_code: segment?.template_code || '',
    prompt_section_text: segment?.prompt_section_text || '',
    schema_definition_json: segment?.schema_definition_json ? JSON.stringify(segment.schema_definition_json, null, 2) : '{}',
    default_category: segment?.default_category || 'core',
    display_order: segment?.display_order || 999,
    default_brevity_level: segment?.default_brevity_level || 'balanced',
    default_terminology_style: segment?.default_terminology_style || 'medical_terms',
    is_required: segment?.is_required || false,
    is_active: segment?.is_active !== undefined ? segment.is_active : true,
  });

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Use pre-loaded consultation types if provided, otherwise fetch
  useEffect(() => {
    if (preloadedConsultationTypes && preloadedConsultationTypes.length > 0) {
      setConsultationTypes(preloadedConsultationTypes);
    } else {
      loadConsultationTypes();
    }
  }, [preloadedConsultationTypes]);

  useEffect(() => {
    if (assignmentType === 'template') {
      loadTemplates();
    }
  }, [assignmentType, formData.consultation_type_code]);

  useEffect(() => {
    if (useClone && !isEditMode) {
      loadSegmentsForCloning();
    }
  }, [useClone, isEditMode]);

  useEffect(() => {
    if (useCombine && !isEditMode) {
      loadSegmentsForCloning(); // Reuse same loading function
    }
  }, [useCombine, isEditMode]);

  const loadConsultationTypes = async () => {
    // Skip if already have pre-loaded types
    if (preloadedConsultationTypes && preloadedConsultationTypes.length > 0) return;

    try {
      const response = await getConsultationTypes(getAccessToken());
      if (response.success) {
        setConsultationTypes(response.consultation_types);
      }
    } catch (err) {
      console.error('Failed to load consultation types:', err);
    }
  };

  const loadTemplates = async () => {
    if (!formData.consultation_type_code) return;

    try {
      const response = await getTemplates(formData.consultation_type_code as ConsultationTypeCode, undefined, 'all', getAccessToken());
      if (response.success) {
        setAvailableTemplates(response.templates);
        // Set first template as default if none selected
        if (!formData.template_code && response.templates.length > 0) {
          setFormData(prev => ({ ...prev, template_code: response.templates[0].template_code }));
        }
      }
    } catch (err) {
      console.error('Failed to load templates:', err);
    }
  };

  const loadSegmentsForCloning = async () => {
    try {
      // Load all segments with full relationship data for cloning
      // This ensures we can clone from any segment regardless of consultation type
      const response = await getAllSegments(undefined, true, getAccessToken());
      if (response.success) {
        setAvailableSegments(response.segments);
      }
    } catch (err) {
      console.error('Failed to load segments for cloning:', err);
    }
  };

  const handleCloneFromParent = (parentSegmentId: string) => {
    // Find segment by unique ID (not segment_code which can be duplicated)
    const parentSegment = availableSegments.find(s => s.id === parentSegmentId);
    if (parentSegment) {
      // Store both the segment ID (for UI) and segment_code (for API)
      setSelectedParentSegmentId(parentSegmentId);
      setSelectedParentSegment(parentSegment.segment_code);
      // Use the selected source consultation type ID
      setSourceConsultationTypeId(sourceConsultationTypeForClone);
      // Pre-fill form with parent segment data
      setFormData(prev => ({
        ...prev,
        segment_code: '', // Keep empty for user to fill
        segment_name: `${parentSegment.segment_name} (Copy)`,
        prompt_section_text: parentSegment.prompt_section_text,
        schema_definition_json: JSON.stringify(parentSegment.schema_definition_json, null, 2),
        default_category: parentSegment.default_category,
        display_order: parentSegment.display_order,
        default_brevity_level: parentSegment.default_brevity_level,
        default_terminology_style: parentSegment.default_terminology_style,
        is_required: false, // Cloned segments typically not required
      }));
    }
  };

  // Get segments filtered by selected consultation type for combining
  const getFilteredSegmentsForCombine = () => {
    if (!combineConsultationTypeId) return [];
    return availableSegments.filter(seg => {
      if (seg.consultation_types && Array.isArray(seg.consultation_types)) {
        return seg.consultation_types.some((ct: any) =>
          ct.type_id === combineConsultationTypeId
        );
      }
      return false;
    });
  };

  // Check if a segment is selected for combining
  const isSegmentSelectedForCombine = (segmentId: string) => {
    return selectedSegmentsToCombine.some(s => s.segment_id === segmentId);
  };

  // Toggle segment selection for combining
  const toggleSegmentForCombine = (segmentId: string) => {
    if (isSegmentSelectedForCombine(segmentId)) {
      setSelectedSegmentsToCombine(prev => prev.filter(s => s.segment_id !== segmentId));
    } else {
      if (selectedSegmentsToCombine.length >= 5) {
        setError('Maximum 5 segments can be combined at once');
        return;
      }
      setSelectedSegmentsToCombine(prev => [
        ...prev,
        { segment_id: segmentId, consultation_type_id: combineConsultationTypeId }
      ]);
    }
  };

  // Handle combine segments action
  const handleCombineSegments = async () => {
    if (selectedSegmentsToCombine.length < 2) {
      setError('Select at least 2 segments to combine');
      return;
    }
    if (!adminId) {
      setError('Admin ID required for combining segments');
      return;
    }

    setCombining(true);
    setError(null);

    try {
      const response = await combineSegments(
        { segments: selectedSegmentsToCombine },
        adminId,
        getAccessToken()
      );

      if (response.success) {
        // Pre-fill form with merged content
        const combinedNames = response.source_segments.map(s => s.segment_name).join(' + ');
        setFormData(prev => ({
          ...prev,
          segment_code: '', // User needs to provide a unique code
          segment_name: `Combined: ${combinedNames}`,
          prompt_section_text: response.merged_prompt,
          schema_definition_json: JSON.stringify(response.merged_schema, null, 2),
          default_category: 'core',
        }));
        setMergeNotes(response.merge_notes);
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setCombining(false);
    }
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    const { name, value, type } = e.target;
    const checked = (e.target as HTMLInputElement).checked;

    setFormData((prev) => {
      const newData = {
        ...prev,
        [name]: type === 'checkbox' ? checked : type === 'number' ? parseInt(value) : value,
      };

      return newData;
    });
  };

  const handleAssignmentTypeChange = (newType: 'consultation_type' | 'template') => {
    setAssignmentType(newType);

    if (newType === 'template') {
      loadTemplates();
    } else {
      setFormData(prev => ({ ...prev, template_code: '' }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      // Validate assignment
      if (assignmentType === 'consultation_type') {
        if (!formData.consultation_type_code) {
          throw new Error('Session Type is required');
        }
      } else if (assignmentType === 'template') {
        if (!formData.template_code) {
          throw new Error('Template is required for template-specific segments');
        }
      }

      // Parse schema JSON
      let schemaJson;
      try {
        schemaJson = JSON.parse(formData.schema_definition_json);
      } catch (err) {
        throw new Error('Invalid JSON in schema definition');
      }

      if (isPendingApproval) {
        // Approve pending segment by adding schema
        if (!adminId) {
          throw new Error('Admin ID required to approve segments');
        }

        await approveSegmentRequest(segment.id, schemaJson, adminId, getAccessToken());
      } else if (isEditMode) {
        // Update existing segment
        const updateRequest: UpdateSegmentRequest = {
          segment_name: formData.segment_name,
          prompt_section_text: formData.prompt_section_text,
          schema_definition_json: schemaJson,
          default_category: formData.default_category as 'core' | 'additional',
          display_order: formData.display_order,
          default_brevity_level: formData.default_brevity_level as BrevityLevel,
          default_terminology_style: formData.default_terminology_style as TerminologyStyle,
          is_required: formData.is_required,
          is_active: formData.is_active,
        };

        await updateSegment(segment.id, updateRequest, getAccessToken());
      } else {
        // Create new segment (with or without cloning)
        if (useClone && selectedParentSegment && adminId) {
          // Clone from parent segment with tracking
          // Validate that we have the source consultation type ID
          if (!sourceConsultationTypeId) {
            throw new Error('Source session type ID is required for cloning. Please select a parent segment from a specific session type.');
          }
          const cloneRequest: CloneSegmentRequest = {
            parent_segment_code: selectedParentSegment,
            source_consultation_type_id: sourceConsultationTypeId,
            new_segment_code: formData.segment_code,
            new_segment_name: formData.segment_name,
            consultation_type_id: assignmentType === 'consultation_type' || assignmentType === 'template'
              ? consultationTypes.find(ct => ct.type_code === formData.consultation_type_code)?.id
              : undefined,
            template_id: assignmentType === 'template'
              ? availableTemplates.find(t => t.template_code === formData.template_code)?.id
              : undefined,
            // Include edited prompt and schema - backend will use these instead of copying from parent
            prompt_section_text: formData.prompt_section_text,
            schema_definition_json: schemaJson,
          };

          await cloneSegment(cloneRequest, adminId, getAccessToken());
        } else {
          // Create new segment without cloning
          const createRequest: CreateSegmentRequest = {
            segment_code: formData.segment_code,
            segment_name: formData.segment_name,
            consultation_type_code: assignmentType === 'consultation_type' ? formData.consultation_type_code as ConsultationTypeCode : undefined,
            template_code: assignmentType === 'template' ? formData.template_code : undefined,
            prompt_section_text: formData.prompt_section_text,
            schema_definition_json: schemaJson,
            default_category: formData.default_category as 'core' | 'additional',
            display_order: formData.display_order,
            default_brevity_level: formData.default_brevity_level as BrevityLevel,
            default_terminology_style: formData.default_terminology_style as TerminologyStyle,
            is_required: formData.is_required,
            is_active: formData.is_active,
          };

          await createSegment(createRequest, getAccessToken());
        }
      }

      onSuccess();
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8 overflow-y-auto">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full my-8">
        <div className={`${isPendingApproval ? 'bg-indigo-600' : 'bg-blue-600'} text-white p-6 rounded-t-lg`}>
          <h2 className="text-2xl font-bold">
            {isPendingApproval
              ? 'Review & Approve Segment Request'
              : isEditMode
              ? 'Edit Segment'
              : 'Create New Segment'}
          </h2>
          <p className={`${isPendingApproval ? 'text-indigo-100' : 'text-blue-100'} mt-1`}>
            {isPendingApproval
              ? `Add JSON schema to approve segment request: ${segment.segment_code}`
              : isEditMode
              ? `Update segment definition for ${segment.segment_code}`
              : 'Define a new segment for extraction'}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-6">
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

          {/* Clone from Existing Segment Option */}
          {!isEditMode && !isPendingApproval && adminId && !useCombine && (
            <div className="bg-gradient-to-r from-purple-50 to-blue-50 border-2 border-purple-200 rounded-lg p-4">
              <div className="flex items-start">
                <input
                  type="checkbox"
                  checked={useClone}
                  onChange={(e) => {
                    setUseClone(e.target.checked);
                    if (e.target.checked) {
                      setUseCombine(false);
                      setSelectedSegmentsToCombine([]);
                      setCombineConsultationTypeId('');
                      setMergeNotes('');
                    }
                  }}
                  className="h-4 w-4 text-purple-600 focus:ring-purple-500 border-gray-300 rounded mt-1"
                />
                <div className="ml-3 flex-1">
                  <label className="text-sm font-medium text-gray-900 flex items-center gap-2">
                    <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    Clone from Existing Segment
                  </label>
                  <p className="text-xs text-gray-600 mt-1">
                    Start with an existing segment and customize it. Parent-child relationship will be tracked for comparison and updates.
                  </p>

                  {useClone && (
                    <div className="mt-3 space-y-3">
                      {/* Step 1: Select Source Consultation Type */}
                      <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1.5">
                          Step 1: Source Session Type <span className="text-red-500">*</span>
                        </label>
                        <select
                          value={sourceConsultationTypeForClone}
                          onChange={(e) => {
                            setSourceConsultationTypeForClone(e.target.value);
                            // Reset segment selection when source CT changes
                            setSelectedParentSegmentId('');
                            setSelectedParentSegment('');
                            setSourceConsultationTypeId('');
                          }}
                          required
                          className="w-full px-3 py-2 border border-purple-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-sm text-gray-900 bg-white"
                        >
                          <option value="">Select source session type...</option>
                          {getUniqueConsultationTypesFromSegments().map((ct) => (
                            <option key={ct.id} value={ct.id}>
                              {ct.name} ({ct.code})
                            </option>
                          ))}
                        </select>
                        <p className="text-xs text-gray-500 mt-1">
                          Choose the session type containing the segment you want to clone
                        </p>
                      </div>

                      {/* Step 2: Select Segment (only shown after CT is selected) */}
                      {sourceConsultationTypeForClone && (
                        <div>
                          <label className="block text-xs font-medium text-gray-700 mb-1.5">
                            Step 2: Select Parent Segment <span className="text-red-500">*</span>
                          </label>
                          <select
                            value={selectedParentSegmentId}
                            onChange={(e) => handleCloneFromParent(e.target.value)}
                            required
                            className="w-full px-3 py-2 border border-purple-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-sm text-gray-900 bg-white"
                          >
                            <option value="">Choose a segment to clone...</option>
                            {getFilteredSegmentsForClone().map((seg) => (
                              <option key={seg.id} value={seg.id}>
                                {seg.segment_name} ({seg.segment_code}) {seg.is_active === false && '- INACTIVE'}
                              </option>
                            ))}
                          </select>
                          {getFilteredSegmentsForClone().length === 0 && (
                            <p className="text-xs text-amber-600 mt-1">
                              No segments found for this session type
                            </p>
                          )}
                        </div>
                      )}

                      {selectedParentSegmentId && (
                        <p className="text-xs text-purple-700 flex items-center gap-1">
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                          </svg>
                          Form pre-filled with parent data. Edit as needed and provide a new segment code.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Combine Multiple Segments Option */}
          {!isEditMode && !isPendingApproval && adminId && !useClone && (
            <div className="bg-gradient-to-r from-green-50 to-teal-50 border-2 border-green-200 rounded-lg p-4">
              <div className="flex items-start">
                <input
                  type="checkbox"
                  checked={useCombine}
                  onChange={(e) => {
                    setUseCombine(e.target.checked);
                    if (!e.target.checked) {
                      setSelectedSegmentsToCombine([]);
                      setCombineConsultationTypeId('');
                      setMergeNotes('');
                    }
                  }}
                  className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded mt-1"
                />
                <div className="ml-3 flex-1">
                  <label className="text-sm font-medium text-gray-900 flex items-center gap-2">
                    <svg className="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 14v6m-3-3h6M6 10h2a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v2a2 2 0 002 2zm10 0h2a2 2 0 002-2V6a2 2 0 00-2-2h-2a2 2 0 00-2 2v2a2 2 0 002 2zM6 20h2a2 2 0 002-2v-2a2 2 0 00-2-2H6a2 2 0 00-2 2v2a2 2 0 002 2z" />
                    </svg>
                    Combine Multiple Segments (AI-Powered)
                  </label>
                  <p className="text-xs text-gray-600 mt-1">
                    Select 2-5 segments to intelligently merge into one. AI will consolidate prompts and schemas logically.
                  </p>

                  {useCombine && (
                    <div className="mt-3 space-y-3">
                      {/* Step 1: Select Consultation Type */}
                      <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1.5">
                          Step 1: Select Session Type <span className="text-red-500">*</span>
                        </label>
                        <select
                          value={combineConsultationTypeId}
                          onChange={(e) => {
                            setCombineConsultationTypeId(e.target.value);
                            setSelectedSegmentsToCombine([]);
                            setMergeNotes('');
                          }}
                          className="w-full px-3 py-2 border border-green-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent text-sm text-gray-900 bg-white"
                        >
                          <option value="">Select session type...</option>
                          {getUniqueConsultationTypesFromSegments().map((ct) => (
                            <option key={ct.id} value={ct.id}>
                              {ct.name} ({ct.code})
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Step 2: Select Segments to Combine */}
                      {combineConsultationTypeId && (
                        <div>
                          <label className="block text-xs font-medium text-gray-700 mb-1.5">
                            Step 2: Select Segments to Combine ({selectedSegmentsToCombine.length}/5 selected)
                          </label>
                          <div className="max-h-48 overflow-y-auto border border-green-200 rounded-lg bg-white">
                            {getFilteredSegmentsForCombine().length === 0 ? (
                              <p className="p-3 text-xs text-gray-500 italic">No segments found</p>
                            ) : (
                              getFilteredSegmentsForCombine().map((seg) => (
                                <label
                                  key={seg.id}
                                  className={`flex items-center p-2 hover:bg-green-50 cursor-pointer border-b border-green-100 last:border-b-0 ${
                                    isSegmentSelectedForCombine(seg.id) ? 'bg-green-100' : ''
                                  }`}
                                >
                                  <input
                                    type="checkbox"
                                    checked={isSegmentSelectedForCombine(seg.id)}
                                    onChange={() => toggleSegmentForCombine(seg.id)}
                                    className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                  />
                                  <span className="ml-2 text-sm text-gray-900">
                                    {seg.segment_name}
                                    <span className="text-xs text-gray-500 ml-1">({seg.segment_code})</span>
                                  </span>
                                </label>
                              ))
                            )}
                          </div>
                          <p className="text-xs text-gray-500 mt-1">
                            Select 2-5 segments. Their prompts and schemas will be intelligently merged.
                          </p>
                        </div>
                      )}

                      {/* Step 3: Combine Button */}
                      {selectedSegmentsToCombine.length >= 2 && (
                        <div>
                          <button
                            type="button"
                            onClick={handleCombineSegments}
                            disabled={combining}
                            className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                          >
                            {combining ? (
                              <>
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                                Combining with AI...
                              </>
                            ) : (
                              <>
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                </svg>
                                Combine {selectedSegmentsToCombine.length} Segments
                              </>
                            )}
                          </button>
                        </div>
                      )}

                      {/* Merge Notes (shown after combining) */}
                      {mergeNotes && (
                        <div className="bg-green-100 border border-green-300 rounded-lg p-3">
                          <p className="text-xs font-medium text-green-800 mb-1">AI Merge Notes:</p>
                          <p className="text-xs text-green-700">{mergeNotes}</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Segment Code */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Segment Code <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                name="segment_code"
                value={formData.segment_code}
                onChange={handleChange}
                disabled={isEditMode}
                required
                placeholder="e.g., DIAGNOSIS_OP"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed font-mono text-sm text-gray-900"
              />
              <p className="text-xs text-gray-500 mt-1">
                Unique identifier (uppercase, underscores)
              </p>
            </div>

            {/* Segment Name */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Segment Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                name="segment_name"
                value={formData.segment_name}
                onChange={handleChange}
                required
                placeholder="e.g., Diagnosis"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900"
              />
              <p className="text-xs text-gray-500 mt-1">
                Display name for the segment
              </p>
            </div>
          </div>

          {/* Assignment Type Selector */}
          {!isEditMode && (
            <div className="bg-blue-50 border-2 border-blue-200 rounded-lg p-4">
              <label className="block text-sm font-medium text-gray-900 mb-3">
                Segment Assignment <span className="text-red-500">*</span>
              </label>
              <div className="space-y-3">
                <label className="flex items-start cursor-pointer">
                  <input
                    type="radio"
                    checked={assignmentType === 'consultation_type'}
                    onChange={() => handleAssignmentTypeChange('consultation_type')}
                    className="h-4 w-4 text-blue-600 mt-0.5"
                  />
                  <div className="ml-3">
                    <span className="text-sm font-medium text-gray-900">Session Type</span>
                    <p className="text-xs text-gray-600 mt-0.5">
                      Assign to a specific session type (segments linked via junction table)
                    </p>
                  </div>
                </label>

                <label className="flex items-start cursor-pointer">
                  <input
                    type="radio"
                    checked={assignmentType === 'template'}
                    onChange={() => handleAssignmentTypeChange('template')}
                    className="h-4 w-4 text-blue-600 mt-0.5"
                  />
                  <div className="ml-3">
                    <span className="text-sm font-medium text-gray-900">Specific Template</span>
                    <p className="text-xs text-gray-600 mt-0.5">
                      Assign to a specific template (segments linked via junction table)
                    </p>
                  </div>
                </label>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Consultation Type - shown for consultation_type and template assignment */}
            {(assignmentType === 'consultation_type' || assignmentType === 'template') && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Session Type {!isEditMode && <span className="text-red-500">*</span>}
                  {isEditMode && (
                    <span className="ml-2 text-xs font-normal text-gray-500">
                      (read-only)
                    </span>
                  )}
                </label>
                {isEditMode ? (
                  /* In edit mode, show read-only display of assigned consultation types */
                  <div className="w-full px-4 py-2 border border-gray-200 rounded-lg bg-gray-50 text-gray-700">
                    {segment?.consultation_types?.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {segment.consultation_types.map((ct: any) => (
                          <span key={ct.type_code} className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                            {ct.type_name}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-gray-400 italic">Not assigned to any session type</span>
                    )}
                  </div>
                ) : (
                  /* In create mode, show dropdown */
                  <select
                    name="consultation_type_code"
                    value={formData.consultation_type_code}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900"
                  >
                    <option value="">Select session type...</option>
                    {consultationTypes.map((type) => (
                      <option key={type.type_code} value={type.type_code}>
                        {type.type_name}
                      </option>
                    ))}
                  </select>
                )}
                <p className="text-xs text-gray-500 mt-1">
                  {isEditMode
                    ? 'Use the "Assigned to" button in the segments list to manage assignments'
                    : assignmentType === 'template'
                    ? 'Template-specific segment (1-to-1 association)'
                    : 'Segment will be available to all templates of this type'}
                </p>
              </div>
            )}

            {/* Template Selector - only shown for template assignment */}
            {assignmentType === 'template' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Template {!isEditMode && <span className="text-red-500">*</span>}
                  {isEditMode && (
                    <span className="ml-2 text-xs font-normal text-gray-500">
                      (read-only)
                    </span>
                  )}
                </label>
                {isEditMode ? (
                  /* In edit mode, show read-only display of assigned templates */
                  <div className="w-full px-4 py-2 border border-gray-200 rounded-lg bg-gray-50 text-gray-700">
                    {segment?.templates?.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {segment.templates.map((t: any) => (
                          <span key={t.template_code} className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">
                            {t.template_name}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-gray-400 italic">Not assigned to any template</span>
                    )}
                  </div>
                ) : (
                  /* In create mode, show dropdown */
                  <select
                    name="template_code"
                    value={formData.template_code}
                    onChange={handleChange}
                    disabled={!formData.consultation_type_code}
                    required
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed text-gray-900"
                  >
                    <option value="">Select template...</option>
                    {availableTemplates.map((template) => (
                      <option key={template.template_code} value={template.template_code}>
                        {template.template_name} ({template.template_code})
                      </option>
                    ))}
                  </select>
                )}
                <p className="text-xs text-gray-500 mt-1">
                  {isEditMode
                    ? 'Use the "Assigned to" button in the segments list to manage assignments'
                    : 'Segment will only be visible to this specific template'}
                </p>
              </div>
            )}

            {/* Default Category */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Default Category <span className="text-red-500">*</span>
              </label>
              <select
                name="default_category"
                value={formData.default_category}
                onChange={handleChange}
                required
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900"
              >
                <option value="core">CORE - Always extracted</option>
                <option value="additional">ADDITIONAL - Extracted in full mode</option>
                <option value="excluded">EXCLUDED - Hidden from this session type</option>
              </select>
              <p className="text-xs text-gray-500 mt-1">
                Use EXCLUDED to hide a common segment for this session type
              </p>
            </div>

            {/* Display Order */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Display Order
              </label>
              <input
                type="number"
                name="display_order"
                value={formData.display_order}
                onChange={handleChange}
                min={1}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900"
              />
              <p className="text-xs text-gray-500 mt-1">
                Order in which segments are displayed
              </p>
            </div>

            {/* Brevity Level */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Default Brevity Level
              </label>
              <select
                name="default_brevity_level"
                value={formData.default_brevity_level}
                onChange={handleChange}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900"
              >
                <option value="concise">Concise</option>
                <option value="balanced">Balanced</option>
                <option value="detailed">Detailed</option>
              </select>
            </div>

            {/* Terminology Style */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Default Terminology Style
              </label>
              <select
                name="default_terminology_style"
                value={formData.default_terminology_style}
                onChange={handleChange}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900"
              >
                <option value="medical_terms">Medical Terms</option>
                <option value="simple_terms">Simple Terms</option>
                <option value="as_spoken">As Spoken</option>
              </select>
            </div>

            {/* Checkboxes */}
            <div className="space-y-4">
              {/* NOTE: is_required field removed from UI - always defaults to false
                  This prevents validate_segment_configuration RPC from failing
                  when new segments are created without proper CORE category assignment */}

              <div className="flex items-start">
                <input
                  type="checkbox"
                  name="is_active"
                  checked={formData.is_active}
                  onChange={handleChange}
                  className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded mt-1"
                />
                <div className="ml-3">
                  <label className="text-sm font-medium text-gray-700">
                    Active Segment
                  </label>
                  <p className="text-xs text-gray-500 mt-1">
                    When checked, segment is active and available for use. Inactive segments are automatically activated when assigned to session types or templates.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Prompt Section Text */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Prompt Section Text <span className="text-red-500">*</span>
              {isEditMode && assignmentType === 'consultation_type' && segment?.consultation_types?.length > 1 && (
                <span className="ml-2 text-xs font-normal text-orange-600">
                  ⚠️ Global field - affects ALL session types
                </span>
              )}
            </label>
            <textarea
              name="prompt_section_text"
              value={formData.prompt_section_text}
              onChange={handleChange}
              required
              rows={6}
              placeholder="Enter the prompt text for extracting this segment..."
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm text-gray-900"
            />
            <p className="text-xs text-gray-500 mt-1">
              {isPendingApproval
                ? 'Description from counsellor (you can edit this)'
                : isEditMode && assignmentType === 'consultation_type' && segment?.consultation_types?.length > 1
                ? '⚠️ Changes to prompt affect ALL associated session types (global field)'
                : 'Instructions for AI to extract this segment from transcript'}
            </p>
          </div>

          {/* Schema Definition JSON */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Schema Definition JSON <span className="text-red-500">*</span>
              {isPendingApproval && (
                <span className="ml-2 text-xs font-normal text-indigo-600 bg-indigo-100 px-2 py-0.5 rounded">
                  Focus here to approve
                </span>
              )}
              {isEditMode && assignmentType === 'consultation_type' && segment?.consultation_types?.length > 1 && (
                <span className="ml-2 text-xs font-normal text-orange-600">
                  ⚠️ Global field - affects ALL session types
                </span>
              )}
            </label>
            <textarea
              name="schema_definition_json"
              value={formData.schema_definition_json}
              onChange={handleChange}
              required
              rows={10}
              placeholder='{"type": "object", "properties": {...}}'
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent font-mono text-xs text-gray-900"
            />
            <p className="text-xs text-gray-500 mt-1">
              {isPendingApproval
                ? 'Add the JSON schema to activate this segment for the counsellor'
                : isEditMode && assignmentType === 'consultation_type' && segment?.consultation_types?.length > 1
                ? '⚠️ Changes to schema affect ALL associated session types (global field)'
                : 'JSON schema definition for this segment\'s structure'}
            </p>
          </div>

          {/* Approval Notice */}
          {isPendingApproval && (
            <div className="bg-indigo-50 border-2 border-indigo-200 rounded-lg p-4">
              <div className="flex items-start">
                <svg
                  className="w-5 h-5 text-indigo-600 mr-2 mt-0.5 flex-shrink-0"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
                    clipRule="evenodd"
                  />
                </svg>
                <div>
                  <p className="text-sm font-medium text-indigo-900">
                    Approval Workflow
                  </p>
                  <p className="text-xs text-indigo-800 mt-1">
                    Review and edit the counsellor's request details as needed. Add or modify the JSON schema
                    and click "Approve Segment" to activate this segment for use in extraction.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200">
            <button
              type="button"
              onClick={onCancel}
              disabled={saving}
              className="px-6 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className={`px-6 py-2 ${
                isPendingApproval
                  ? 'bg-indigo-600 hover:bg-indigo-700'
                  : 'bg-blue-600 hover:bg-blue-700'
              } text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2`}
            >
              {saving && (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
              )}
              {saving
                ? isPendingApproval
                  ? 'Approving...'
                  : 'Saving...'
                : isPendingApproval
                ? 'Approve Segment'
                : isEditMode
                ? 'Update Segment'
                : 'Create Segment'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
