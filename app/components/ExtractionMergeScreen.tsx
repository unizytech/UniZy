"use client";

import React, { useState, useEffect, useRef } from 'react';
import {
  mergeExtractions,
  previewMerge,
  getPatientTimeline,
  type MergeRequest,
  type MergeResponse,
  type PatientTimelineExtraction,
  type UploadedJsonSource,
} from '../services/mergeService';
import { getDoctorTemplates } from '@lib/summaryApi';
import { searchPatients, type PatientSearchResult } from '@lib/patientHistoryApi';
import { useAuth } from '@lib/auth';
import type { MergeTargetTemplate } from '@lib/types';
import DoctorSelector from './DoctorSelector';

interface ExtractionMergeScreenProps {
  initialPatientId?: string;
  initialDoctorId?: string;
  onClose?: () => void;
}

export default function ExtractionMergeScreen({
  initialPatientId,
  initialDoctorId,
  onClose,
}: ExtractionMergeScreenProps) {
  const { getAccessToken } = useAuth();

  // State
  const [patientId, setPatientId] = useState(initialPatientId || '');
  const [extractions, setExtractions] = useState<PatientTimelineExtraction[]>([]);
  const [selectedExtractionIds, setSelectedExtractionIds] = useState<string[]>([]);
  const [targetTemplateCode, setTargetTemplateCode] = useState('');
  const [doctorId, setDoctorId] = useState(initialDoctorId || '');
  const [mergeNotes, setMergeNotes] = useState('');

  // Patient list for dropdown
  const [patientsList, setPatientsList] = useState<PatientSearchResult[]>([]);
  const [loadingPatients, setLoadingPatients] = useState(false);

  // Templates from database (doctor-accessible templates)
  const [templates, setTemplates] = useState<MergeTargetTemplate[]>([]);
  const [loadingTypes, setLoadingTypes] = useState(true);

  // JSON Upload state
  const [uploadedJsonSources, setUploadedJsonSources] = useState<UploadedJsonSource[]>([]);
  const [jsonSourceName, setJsonSourceName] = useState('External Data');
  const [uploadType, setUploadType] = useState<string>('OTHER');
  const [jsonError, setJsonError] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<MergeResponse | null>(null);
  const [mergedResult, setMergedResult] = useState<MergeResponse | null>(null);

  // Upload type options - determines merge strategy
  // DEEP_MERGE: Contextual merging, latest/most complete value wins
  // APPEND: Arrays concatenated, never replaced
  const UPLOAD_TYPES = [
    // DEEP_MERGE types
    { value: 'OP_SUMMARY', label: 'OP Summary', strategy: 'DEEP_MERGE', description: 'Outpatient session summary' },
    { value: 'DISCHARGE_SUMMARY', label: 'Discharge Summary', strategy: 'DEEP_MERGE', description: 'School discharge summary' },
    { value: 'EXAMINATION', label: 'Examination', strategy: 'DEEP_MERGE', description: 'Physical examination, vitals' },
    { value: 'OPTOMETRY', label: 'Optometry', strategy: 'DEEP_MERGE', description: 'Ophthalmology/optometry data' },
    { value: 'OTHER', label: 'Other', strategy: 'DEEP_MERGE', description: 'General/unclassified data' },
    // APPEND types
    { value: 'INVESTIGATION', label: 'Investigation/Lab', strategy: 'APPEND', description: 'Lab results, imaging reports' },
    { value: 'PRESCRIPTION', label: 'Prescription', strategy: 'APPEND', description: 'Medications, prescriptions' },
    { value: 'NOTES', label: 'Notes', strategy: 'APPEND', description: 'Clinical notes, documentation' },
  ];

  // Load templates when doctorId is available
  useEffect(() => {
    const loadTemplates = async () => {
      if (!doctorId) {
        setLoadingTypes(false);
        return;
      }
      try {
        setLoadingTypes(true);
        const response = await getDoctorTemplates(doctorId, getAccessToken());
        if (response.success && response.templates) {
          setTemplates(response.templates);
          // Set default target template to first available template
          if (response.templates.length > 0 && !targetTemplateCode) {
            setTargetTemplateCode(response.templates[0].template_code);
          }
        }
      } catch (err) {
        console.error('Failed to load templates:', err);
        // Fallback to empty list - user will see "No templates available"
      } finally {
        setLoadingTypes(false);
      }
    };
    loadTemplates();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doctorId]); // Only re-run when doctorId changes - getAccessToken is stable from useAuth

  // Load patients list when doctor is selected
  useEffect(() => {
    if (doctorId) {
      loadPatientsList();
    } else {
      setPatientsList([]);
      setPatientId('');
      setExtractions([]);
      setSelectedExtractionIds([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doctorId]);

  const loadPatientsList = async () => {
    if (!doctorId) return;

    try {
      setLoadingPatients(true);
      const accessToken = getAccessToken();
      // Use searchPatients with empty query to get all patients for this doctor
      const response = await searchPatients('', doctorId, 1, 100, accessToken);
      setPatientsList(response.patients || []);
    } catch (err) {
      console.error('Failed to load patients:', err);
      setPatientsList([]);
    } finally {
      setLoadingPatients(false);
    }
  };

  // Load patient timeline when patient ID changes (with debounce to avoid too many API calls)
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  useEffect(() => {
    // Clear any existing timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Only load if patientId has at least 2 characters
    if (patientId && patientId.length >= 2) {
      debounceTimerRef.current = setTimeout(() => {
        loadPatientTimeline();
      }, 500); // 500ms debounce
    }

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [patientId]);

  const loadPatientTimeline = async () => {
    try {
      setLoading(true);
      setError(null);
      const timeline = await getPatientTimeline(patientId, undefined, getAccessToken());
      setExtractions(timeline.extractions);
      setSelectedExtractionIds([]); // Reset selection
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load student timeline');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectExtraction = (extractionId: string) => {
    setSelectedExtractionIds((prev) =>
      prev.includes(extractionId)
        ? prev.filter((id) => id !== extractionId)
        : [...prev, extractionId]
    );
  };

  const handleSelectAll = () => {
    if (selectedExtractionIds.length === extractions.length) {
      setSelectedExtractionIds([]);
    } else {
      setSelectedExtractionIds(extractions.map((e) => e.extraction_id));
    }
  };

  // Handle JSON file upload - adds to uploadedJsonSources array
  const handleJsonFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setJsonError(null);

    // Check source limit (max 4 total, including DB extractions)
    const totalSources = selectedExtractionIds.length + uploadedJsonSources.length;
    if (totalSources >= 4) {
      setJsonError('Maximum 4 sources allowed (extractions + JSON uploads combined)');
      event.target.value = '';
      return;
    }

    try {
      const text = await file.text();
      const parsedJson = JSON.parse(text);

      // Validate it's an object (not array or primitive)
      if (typeof parsedJson !== 'object' || Array.isArray(parsedJson) || parsedJson === null) {
        throw new Error('JSON must be an object with key-value pairs');
      }

      // Auto-generate source name from filename if default
      let sourceName = jsonSourceName;
      if (jsonSourceName === 'External Data') {
        sourceName = file.name.replace('.json', '').replace(/[_-]/g, ' ');
      }

      // Add to array (supports multiple JSON sources)
      const newSource: UploadedJsonSource = {
        data: parsedJson,
        source_name: sourceName,
        upload_type: uploadType as any, // UploadType from mergeService
      };

      setUploadedJsonSources(prev => [...prev, newSource]);

      // Reset inputs for next upload
      setJsonSourceName('External Data');
    } catch (err) {
      setJsonError(err instanceof Error ? err.message : 'Invalid JSON file');
    }

    // Reset file input
    event.target.value = '';
  };

  // Clear all uploaded JSON sources
  const handleClearAllJson = () => {
    setUploadedJsonSources([]);
    setJsonError(null);
    setJsonSourceName('External Data');
    setUploadType('OTHER');
  };

  // Remove a specific JSON source by index
  const handleRemoveJsonSource = (index: number) => {
    setUploadedJsonSources(prev => prev.filter((_, i) => i !== index));
  };

  const handlePreview = async () => {
    // Calculate total sources (extractions + uploaded JSON sources)
    const totalSources = selectedExtractionIds.length + uploadedJsonSources.length;
    if (totalSources < 2) {
      setError('Please select at least 2 sources to merge (extractions + JSON uploads)');
      return;
    }
    if (totalSources > 4) {
      setError('Maximum 4 sources allowed (extractions + JSON uploads combined)');
      return;
    }
    // For JSON-only merge, patient_id is required
    if (selectedExtractionIds.length === 0 && !patientId) {
      setError('Student ID is required for JSON-only merge');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const preview = await previewMerge({
        source_extraction_ids: selectedExtractionIds,
        target_template_code: targetTemplateCode,
        doctor_id: doctorId,
        uploaded_json_sources: uploadedJsonSources.length > 0 ? uploadedJsonSources : undefined,
        patient_id: selectedExtractionIds.length === 0 ? patientId : undefined,
      }, getAccessToken());
      setPreviewData(preview);
      setMergedResult(null); // Clear any previous merged result
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to preview merge');
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmMerge = async () => {
    // Calculate total sources (extractions + uploaded JSON sources)
    const totalSources = selectedExtractionIds.length + uploadedJsonSources.length;
    if (totalSources < 2) {
      setError('Please select at least 2 sources to merge (extractions + JSON uploads)');
      return;
    }
    if (totalSources > 4) {
      setError('Maximum 4 sources allowed (extractions + JSON uploads combined)');
      return;
    }
    // For JSON-only merge, patient_id is required
    if (selectedExtractionIds.length === 0 && !patientId) {
      setError('Student ID is required for JSON-only merge');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const request: MergeRequest = {
        source_extraction_ids: selectedExtractionIds,
        target_template_code: targetTemplateCode,
        doctor_id: doctorId,
        merge_notes: mergeNotes || undefined,
        uploaded_json_sources: uploadedJsonSources.length > 0 ? uploadedJsonSources : undefined,
        patient_id: selectedExtractionIds.length === 0 ? patientId : undefined,
      };
      const result = await mergeExtractions(request, getAccessToken());
      setMergedResult(result);
      setPreviewData(null); // Clear preview
      handleClearAllJson(); // Clear uploaded JSON sources after successful merge

      // Reload timeline to show new merged extraction
      await loadPatientTimeline();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to merge extractions');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Merge Extractions</h1>
            <p className="text-gray-600 mt-1">
              Combine multiple medical extractions into a single consolidated record
            </p>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            >
              Close
            </button>
          )}
        </div>

        {/* Error Display */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
            <div className="flex items-start">
              <svg
                className="w-5 h-5 text-red-600 mt-0.5 mr-3"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
              <div>
                <h3 className="text-sm font-medium text-red-800">Error</h3>
                <p className="text-sm text-red-700 mt-1">{error}</p>
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Panel: Patient Selection & Configuration */}
          <div className="lg:col-span-1 space-y-6">
            {/* Doctor Selection */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Counsellor Selection</h2>
              <DoctorSelector
                selectedDoctorId={doctorId}
                onDoctorSelect={(id) => {
                  setDoctorId(id || '');
                  // Clear patient selection when doctor changes
                  setPatientId('');
                  setExtractions([]);
                  setSelectedExtractionIds([]);
                }}
                required
              />
            </div>

            {/* Patient Selection */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Student Selection</h2>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Student ID
                </label>
                {!doctorId ? (
                  <p className="text-sm text-gray-500 italic">Select a counsellor first</p>
                ) : loadingPatients ? (
                  <div className="flex items-center justify-center py-3">
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500 mr-2"></div>
                    <span className="text-gray-500 text-sm">Loading students...</span>
                  </div>
                ) : patientsList.length > 0 ? (
                  <select
                    value={patientId}
                    onChange={(e) => setPatientId(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                  >
                    <option value="">Select a student...</option>
                    {patientsList.map((patient) => (
                      <option key={patient.id} value={patient.patient_id}>
                        {patient.patient_id}
                        {patient.full_name ? ` - ${patient.full_name}` : ''}
                        {patient.hospital_name ? ` (${patient.hospital_name})` : ''}
                        {patient.add_info?.roomNo ? ` [Room ${patient.add_info.roomNo}, Bed ${patient.add_info.bedNo}]` : ''}
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="text-sm text-gray-500 italic">No students found for this counsellor</p>
                )}
                {patientId && (
                  <button
                    onClick={loadPatientTimeline}
                    disabled={!patientId || loading}
                    className="mt-3 w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                  >
                    {loading ? 'Loading...' : 'Load Timeline'}
                  </button>
                )}
              </div>
            </div>

            {/* Merge Configuration */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Merge Configuration</h2>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Target Template
                  </label>
                  <select
                    value={targetTemplateCode}
                    onChange={(e) => setTargetTemplateCode(e.target.value)}
                    disabled={loadingTypes || !doctorId}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 disabled:bg-gray-100"
                  >
                    {!doctorId ? (
                      <option value="">Select counsellor first</option>
                    ) : loadingTypes ? (
                      <option value="">Loading templates...</option>
                    ) : templates.length === 0 ? (
                      <option value="">No templates available</option>
                    ) : (
                      templates.map((template) => (
                        <option key={template.template_code} value={template.template_code}>
                          {template.template_name}{template.is_common ? ' (Common)' : ''}
                        </option>
                      ))
                    )}
                  </select>
                  <p className="text-xs text-gray-500 mt-1">
                    Choose the template for the merged output ({templates.length} templates available)
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Merge Notes (Optional)
                  </label>
                  <textarea
                    value={mergeNotes}
                    onChange={(e) => setMergeNotes(e.target.value)}
                    placeholder="Add notes about this merge..."
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 placeholder:text-gray-400"
                  />
                </div>

                <div className="pt-4 border-t border-gray-200">
                  <p className="text-sm text-gray-600 mb-2">
                    <strong>Selected:</strong> {selectedExtractionIds.length} extraction(s)
                    {uploadedJsonSources.length > 0 && (
                      <span className="text-purple-600"> + {uploadedJsonSources.length} JSON upload(s)</span>
                    )}
                    <span className="text-gray-400 ml-2">
                      ({selectedExtractionIds.length + uploadedJsonSources.length}/4 max)
                    </span>
                  </p>

                  {!doctorId && (
                    <p className="text-sm text-amber-600 mb-2">
                      Warning: Counsellor not selected. Please select a counsellor above.
                    </p>
                  )}

                  {selectedExtractionIds.length === 0 && uploadedJsonSources.length > 0 && !patientId && (
                    <p className="text-sm text-amber-600 mb-2">
                      Warning: Student ID required for JSON-only merge (no DB extractions selected).
                    </p>
                  )}

                  <button
                    onClick={handlePreview}
                    disabled={
                      (selectedExtractionIds.length + uploadedJsonSources.length) < 2 ||
                      (selectedExtractionIds.length === 0 && !patientId) ||
                      !doctorId ||
                      loading
                    }
                    className="w-full mb-2 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                  >
                    {loading ? 'Processing...' : 'Preview Merge'}
                  </button>

                  <button
                    onClick={handleConfirmMerge}
                    disabled={
                      (selectedExtractionIds.length + uploadedJsonSources.length) < 2 ||
                      (selectedExtractionIds.length === 0 && !patientId) ||
                      !doctorId ||
                      loading
                    }
                    className="w-full px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                  >
                    {loading ? 'Processing...' : 'Confirm & Save Merge'}
                  </button>
                </div>
              </div>
            </div>

            {/* JSON Upload Section */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Add JSON Data
                <span className="ml-2 text-xs font-normal text-gray-500">(Optional - up to 4 total sources)</span>
              </h2>
              <p className="text-sm text-gray-600 mb-4">
                Upload external JSON data to merge. Merge strategy depends on <strong>Upload Type</strong>.
              </p>

              {/* JSON Source Configuration */}
              <div className="space-y-3 mb-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Source Name
                  </label>
                  <input
                    type="text"
                    value={jsonSourceName}
                    onChange={(e) => setJsonSourceName(e.target.value)}
                    placeholder="e.g., External Lab Report"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-gray-900 placeholder:text-gray-400 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Upload Type
                  </label>
                  <select
                    value={uploadType}
                    onChange={(e) => setUploadType(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-gray-900 text-sm"
                  >
                    <optgroup label="DEEP_MERGE (Latest wins for conflicts)">
                      {UPLOAD_TYPES.filter(t => t.strategy === 'DEEP_MERGE').map((type) => (
                        <option key={type.value} value={type.value}>
                          {type.label} - {type.description}
                        </option>
                      ))}
                    </optgroup>
                    <optgroup label="APPEND (Arrays concatenated)">
                      {UPLOAD_TYPES.filter(t => t.strategy === 'APPEND').map((type) => (
                        <option key={type.value} value={type.value}>
                          {type.label} - {type.description}
                        </option>
                      ))}
                    </optgroup>
                  </select>
                  <p className="text-xs text-gray-500 mt-1">
                    {UPLOAD_TYPES.find(t => t.value === uploadType)?.strategy === 'APPEND'
                      ? 'APPEND: Data will be added without replacing existing values'
                      : 'DEEP_MERGE: Latest/most complete value wins for conflicts'}
                  </p>
                </div>
              </div>

              {/* File Upload */}
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Upload JSON File
                </label>
                <div className="flex items-center space-x-3">
                  <label className={`flex-1 ${(selectedExtractionIds.length + uploadedJsonSources.length) >= 4 ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}>
                    <div className={`w-full px-4 py-3 border-2 border-dashed rounded-lg text-center transition-colors ${
                      (selectedExtractionIds.length + uploadedJsonSources.length) >= 4
                        ? 'border-gray-200 bg-gray-50'
                        : 'border-gray-300 hover:border-purple-400 hover:bg-purple-50'
                    }`}>
                      <svg className="mx-auto h-8 w-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                      </svg>
                      <span className="text-sm text-gray-600 mt-1 block">
                        {(selectedExtractionIds.length + uploadedJsonSources.length) >= 4
                          ? 'Maximum 4 sources reached'
                          : 'Click to upload or drag & drop'}
                      </span>
                      <span className="text-xs text-gray-500">.json file only</span>
                    </div>
                    <input
                      type="file"
                      accept=".json,application/json"
                      onChange={handleJsonFileUpload}
                      disabled={(selectedExtractionIds.length + uploadedJsonSources.length) >= 4}
                      className="hidden"
                    />
                  </label>
                </div>
              </div>

              {/* JSON Error */}
              {jsonError && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-sm text-red-700">{jsonError}</p>
                </div>
              )}

              {/* Uploaded JSON Sources List */}
              {uploadedJsonSources.length > 0 && (
                <div className="mb-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-medium text-gray-700">
                      Uploaded JSON Sources ({uploadedJsonSources.length})
                    </h3>
                    <button
                      onClick={handleClearAllJson}
                      className="text-red-600 hover:text-red-800 text-xs"
                    >
                      Clear All
                    </button>
                  </div>
                  {uploadedJsonSources.map((source, index) => (
                    <div key={index} className="p-3 bg-purple-50 border border-purple-200 rounded-lg">
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center">
                          <svg className="w-4 h-4 text-purple-600 mr-2" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                          </svg>
                          <span className="text-sm font-medium text-purple-800">
                            {source.source_name || `Source ${index + 1}`}
                          </span>
                          <span className={`ml-2 px-2 py-0.5 text-xs rounded ${
                            UPLOAD_TYPES.find(t => t.value === source.upload_type)?.strategy === 'APPEND'
                              ? 'bg-green-200 text-green-800'
                              : 'bg-purple-200 text-purple-800'
                          }`}>
                            {source.upload_type}
                          </span>
                        </div>
                        <button
                          onClick={() => handleRemoveJsonSource(index)}
                          className="text-purple-600 hover:text-purple-800 text-xs"
                        >
                          Remove
                        </button>
                      </div>
                      <p className="text-xs text-purple-600">
                        {Object.keys(source.data).length} fields |{' '}
                        {UPLOAD_TYPES.find(t => t.value === source.upload_type)?.strategy || 'DEEP_MERGE'} strategy
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {/* Info Box */}
              <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                <div className="flex">
                  <svg className="w-5 h-5 text-blue-600 mt-0.5 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                  </svg>
                  <div className="text-xs text-blue-700">
                    <strong>Merge Strategies:</strong><br />
                    <span className="text-purple-700">DEEP_MERGE</span>: Contextual merging, latest value wins for conflicts<br />
                    <span className="text-green-700">APPEND</span>: Arrays are concatenated, never replaced
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Middle Panel: Extraction Timeline */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-gray-900">
                  Student Extraction Timeline
                </h2>
                {extractions.length > 0 && (
                  <button
                    onClick={handleSelectAll}
                    className="text-sm text-blue-600 hover:text-blue-700"
                  >
                    {selectedExtractionIds.length === extractions.length
                      ? 'Deselect All'
                      : 'Select All'}
                  </button>
                )}
              </div>

              {loading && extractions.length === 0 ? (
                <div className="text-center py-12">
                  <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                  <p className="text-gray-600 mt-2">Loading extractions...</p>
                </div>
              ) : extractions.length === 0 ? (
                <div className="text-center py-12">
                  <svg
                    className="mx-auto h-12 w-12 text-gray-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                    />
                  </svg>
                  <p className="text-gray-600 mt-4">
                    {patientId
                      ? 'No extractions found for this student'
                      : 'Enter a student ID to load extractions'}
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {extractions.map((extraction) => (
                    <div
                      key={extraction.extraction_id}
                      className={`border rounded-lg p-4 cursor-pointer transition-all ${
                        selectedExtractionIds.includes(extraction.extraction_id)
                          ? 'border-blue-500 bg-blue-50'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                      onClick={() => handleSelectExtraction(extraction.extraction_id)}
                    >
                      <div className="flex items-start">
                        <input
                          type="checkbox"
                          checked={selectedExtractionIds.includes(extraction.extraction_id)}
                          onChange={() => handleSelectExtraction(extraction.extraction_id)}
                          className="mt-1 mr-3 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                        />
                        <div className="flex-1">
                          <div className="flex items-center justify-between">
                            <h3 className="text-sm font-medium text-gray-900">
                              {extraction.consultation_type_name}
                              {extraction.is_merged && (
                                <span className="ml-2 px-2 py-0.5 text-xs bg-purple-100 text-purple-800 rounded">
                                  Merged ({extraction.source_count} sources)
                                </span>
                              )}
                            </h3>
                            <span className="text-xs text-gray-500">
                              {formatDate(extraction.created_at)}
                            </span>
                          </div>
                          <div className="mt-1 text-sm text-gray-600">
                            <span>Counsellor: {extraction.doctor_name || 'Unknown'}</span>
                            <span className="mx-2">•</span>
                            <span>{extraction.segment_count} segments</span>
                          </div>
                          <div className="mt-1">
                            <span className="inline-flex items-center px-2 py-0.5 text-xs bg-gray-100 text-gray-800 rounded">
                              {extraction.consultation_type_code}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Preview/Result Display */}
            {(previewData || mergedResult) && (
              <div className="mt-6 bg-white rounded-lg shadow p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-gray-900">
                    {previewData ? 'Merge Preview' : 'Merged Result'}
                  </h2>
                  <button
                    onClick={() => {
                      setPreviewData(null);
                      setMergedResult(null);
                    }}
                    className="text-sm text-gray-600 hover:text-gray-700"
                  >
                    Close
                  </button>
                </div>

                {previewData && (
                  <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                    <p className="text-sm text-yellow-800">
                      <strong>Preview Mode:</strong> This is a preview. Click "Confirm & Save
                      Merge" to save the merged extraction.
                    </p>
                  </div>
                )}

                {mergedResult && mergedResult.extraction_id && (
                  <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
                    <p className="text-sm text-green-800">
                      <strong>Success!</strong> Merged extraction created with ID:{' '}
                      <code className="bg-green-100 px-1 py-0.5 rounded">
                        {mergedResult.extraction_id}
                      </code>
                    </p>
                  </div>
                )}

                {/* Metadata */}
                {(previewData || mergedResult)?.merge_metadata && (
                  <div className="mb-4 p-4 bg-gray-50 rounded-lg">
                    <h3 className="text-sm font-semibold text-gray-900 mb-2">Merge Metadata</h3>
                    <dl className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <dt className="text-gray-600">Source Count:</dt>
                        <dd className="font-medium">
                          {(previewData || mergedResult)?.merge_metadata?.source_count ?? 'N/A'}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-gray-600">Target Template:</dt>
                        <dd className="font-medium">
                          {(previewData || mergedResult)?.merge_metadata?.target_template_code ?? 'N/A'}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-gray-600">Conflicts Detected:</dt>
                        <dd className="font-medium">
                          {(previewData || mergedResult)?.merge_metadata?.conflict_count ?? 'N/A'}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-gray-600">Merge Scenario:</dt>
                        <dd className="font-medium">
                          {(previewData || mergedResult)?.merge_metadata?.cross_type_scenario ?? 'N/A'}
                        </dd>
                      </div>
                    </dl>
                  </div>
                )}

                {/* Merged Data */}
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 mb-2">Merged Data</h3>
                  <div className="max-h-96 overflow-y-auto border border-gray-200 rounded-lg p-4 bg-gray-50">
                    <pre className="text-xs text-gray-800 whitespace-pre-wrap">
                      {JSON.stringify(
                        (previewData || mergedResult)?.merged_data,
                        null,
                        2
                      )}
                    </pre>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
