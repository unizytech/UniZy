'use client';

import React, { useState, useEffect } from 'react';
import type { ConsultationTypeCode, Template } from '@lib/types';
import {
  createTemplate,
  updateTemplate,
  getConsultationTypes,
  getTemplates,
  handleApiError,
  listSourceTemplates,
  importTemplateFromSource,
  type CreateTemplateData,
  type UpdateTemplateData,
  type SourceTemplate,
  type ImportTemplateResult,
} from '@lib/summaryApi';
import { useAuth } from '@lib/auth';

interface TemplateFormProps {
  template?: Template; // If provided, edit mode
  consultationTypeCode: ConsultationTypeCode;
  userId?: string;
  onSuccess: () => void;
  onCancel: () => void;
}

export function TemplateForm({
  template,
  consultationTypeCode,
  userId,
  onSuccess,
  onCancel,
}: TemplateFormProps) {
  const { getAccessToken } = useAuth();
  const authToken = getAccessToken();
  const isEditMode = !!template;

  // Form state
  const [templateCode, setTemplateCode] = useState(template?.template_code || '');
  const [templateName, setTemplateName] = useState(template?.template_name || '');
  const [description, setDescription] = useState(template?.description || '');
  const [useCase, setUseCase] = useState(template?.use_case || '');
  const [specialization, setSpecialization] = useState(template?.specialization || '');
  const [estimatedTime, setEstimatedTime] = useState<string>(
    template?.estimated_extraction_time_seconds?.toString() || ''
  );

  // Inheritance configuration
  const [inheritFromType, setInheritFromType] = useState<'none' | 'consultation_type' | 'template'>('consultation_type');
  const [inheritFromId, setInheritFromId] = useState<string>(consultationTypeCode);

  // Available options for inheritance
  const [consultationTypes, setConsultationTypes] = useState<any[]>([]);
  const [availableTemplates, setAvailableTemplates] = useState<Template[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(false);

  // Active status (create only)
  const [isActive, setIsActive] = useState(true);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Import-from-source state (create mode only)
  const [mode, setMode] = useState<'create' | 'import'>('create');
  const [sourceTemplates, setSourceTemplates] = useState<SourceTemplate[] | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [selectedSourceCode, setSelectedSourceCode] = useState<string>('');
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<ImportTemplateResult | null>(null);

  // Log consultationTypeCode prop on mount and changes
  useEffect(() => {
    console.log('[TEMPLATE_FORM] Component mounted/updated with consultationTypeCode:', consultationTypeCode);
  }, [consultationTypeCode]);

  // Load consultation types and templates for inheritance options
  useEffect(() => {
    if (!isEditMode && authToken) {
      loadInheritanceOptions();
    }
  }, [isEditMode, authToken]);

  const loadInheritanceOptions = async () => {
    try {
      setLoadingOptions(true);

      const accessToken = getAccessToken();
      if (!accessToken) {
        console.warn('[TemplateForm] Auth token not available, skipping inheritance options load');
        return;
      }

      // Load all consultation types (requires admin auth)
      const typesResponse = await getConsultationTypes(accessToken);
      if (typesResponse.success) {
        setConsultationTypes(typesResponse.consultation_types);
      }

      // Load all templates for the current consultation type
      const templatesResponse = await getTemplates(consultationTypeCode, userId, undefined, accessToken);
      if (templatesResponse.success) {
        setAvailableTemplates(templatesResponse.templates);
      }
    } catch (err) {
      console.error('Failed to load inheritance options:', err);
    } finally {
      setLoadingOptions(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      if (isEditMode) {
        // Update existing template
        const updateData: UpdateTemplateData = {
          template_name: templateName || undefined,
          description: description || undefined,
          specialization: specialization || undefined,
          use_case: useCase || undefined,
          estimated_extraction_time_seconds: estimatedTime
            ? parseFloat(estimatedTime)
            : undefined,
        };

        await updateTemplate(template.template_code, updateData, getAccessToken());
      } else {
        // Create new template
        console.log('[TEMPLATE_FORM] Creating template with:');
        console.log('[TEMPLATE_FORM] consultationTypeCode prop:', consultationTypeCode);
        console.log('[TEMPLATE_FORM] templateCode:', templateCode);
        console.log('[TEMPLATE_FORM] inheritFromType:', inheritFromType);
        console.log('[TEMPLATE_FORM] inheritFromId:', inheritFromId);

        // IMPORTANT: When inheriting from a consultation type, the template should BELONG to
        // that consultation type (not the originally selected one in the parent component)
        // This ensures the template shows up under the correct consultation type filter
        const effectiveConsultationTypeCode =
          inheritFromType === 'consultation_type' && inheritFromId
            ? inheritFromId as ConsultationTypeCode
            : consultationTypeCode;

        console.log('[TEMPLATE_FORM] effectiveConsultationTypeCode:', effectiveConsultationTypeCode);

        const createData: CreateTemplateData = {
          template_code: templateCode,
          template_name: templateName,
          description,
          consultation_type_code: effectiveConsultationTypeCode,
          specialization: specialization || undefined,
          use_case: useCase || undefined,
          estimated_extraction_time_seconds: estimatedTime
            ? parseFloat(estimatedTime)
            : undefined,
          is_active: isActive,
          inherit_from_type: inheritFromType === 'none' ? undefined : inheritFromType,
          inherit_from_id: inheritFromType === 'none' ? undefined : inheritFromId,
        };

        console.log('[TEMPLATE_FORM] Final createData:', JSON.stringify(createData, null, 2));

        await createTemplate(createData, userId, getAccessToken());
      }

      onSuccess();
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const enterImportMode = async () => {
    setMode('import');
    setImportError(null);
    setImportResult(null);
    if (sourceTemplates !== null) return; // already loaded
    setSourceLoading(true);
    try {
      const rows = await listSourceTemplates(authToken);
      setSourceTemplates(rows);
      if (rows.length && !selectedSourceCode) setSelectedSourceCode(rows[0].template_code);
    } catch (err) {
      setImportError(handleApiError(err));
      setSourceTemplates([]);
    } finally {
      setSourceLoading(false);
    }
  };

  const handleImport = async () => {
    if (!selectedSourceCode) return;
    setImportError(null);
    setImportResult(null);
    setImporting(true);
    try {
      const result = await importTemplateFromSource(selectedSourceCode, authToken);
      setImportResult(result);
      // brief pause so admin can see the summary, then close + refresh the list
      setTimeout(() => onSuccess(), 1200);
    } catch (err) {
      setImportError(handleApiError(err));
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="bg-blue-600 text-white p-6 rounded-t-lg flex items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold">
              {isEditMode
                ? 'Edit Template'
                : mode === 'import'
                ? 'Import Template from Source DB'
                : 'Create New Template'}
            </h2>
            <p className="text-blue-100 text-sm mt-1">
              {isEditMode
                ? 'Update template metadata'
                : mode === 'import'
                ? 'Copy a template (and its dependencies) from the configured source project'
                : 'Create a template from scratch or inherit from session type'}
            </p>
          </div>
          {!isEditMode && mode === 'create' && (
            <button
              type="button"
              onClick={enterImportMode}
              className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg font-medium transition-colors shrink-0"
            >
              Import from Source DB
            </button>
          )}
        </div>

        {!isEditMode && mode === 'import' ? (
          <div className="p-6 space-y-4">
            {importError && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <p className="text-red-800 text-sm">{importError}</p>
              </div>
            )}
            {importResult && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-sm text-green-900">
                <p className="font-medium">
                  Imported <span className="font-bold">{importResult.template_code}</span>.
                </p>
                <ul className="mt-2 list-disc list-inside space-y-0.5 text-green-800">
                  <li>Template segments: {importResult.created.template_segments}</li>
                  <li>Segment definitions created: {importResult.created.segment_definitions}</li>
                  <li>Session type segments: {importResult.created.consultation_type_segments}</li>
                  <li>New session type: {importResult.created.consultation_type ? 'yes' : 'no'}</li>
                  <li>New system prompt config: {importResult.created.system_prompt_config ? 'yes' : 'no'}</li>
                  <li>School remapped: {importResult.created.hospital_remapped ? 'yes' : 'no'}</li>
                </ul>
                {importResult.created.assembly_warnings.length > 0 && (
                  <p className="mt-2 text-amber-700">
                    Assembly warnings: {importResult.created.assembly_warnings.join(', ')}
                  </p>
                )}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Source Template <span className="text-red-500">*</span>
              </label>
              {sourceLoading ? (
                <p className="text-gray-500 text-sm">Loading source templates…</p>
              ) : sourceTemplates && sourceTemplates.length > 0 ? (
                <select
                  value={selectedSourceCode}
                  onChange={(e) => setSelectedSourceCode(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                  disabled={importing}
                >
                  {sourceTemplates.map((t) => (
                    <option key={t.template_code} value={t.template_code}>
                      {t.template_name} ({t.template_code})
                      {t.type_code ? ` — ${t.type_code}` : ''}
                      {t.is_active === false ? ' [inactive]' : ''}
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-gray-500 text-sm">No templates available on the source DB.</p>
              )}
              <p className="text-xs text-gray-500 mt-2">
                Imports the template plus any missing segments, consultation type, and system prompt
                rows. Re-assembles prompts on the target after insert. The new template is created
                as a global (doctor_id = NULL) template.
              </p>
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
              <button
                type="button"
                onClick={() => setMode('create')}
                disabled={importing}
                className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium transition-colors"
              >
                Back
              </button>
              <button
                type="button"
                onClick={handleImport}
                disabled={importing || !selectedSourceCode}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {importing ? 'Importing…' : 'Import'}
              </button>
            </div>
          </div>
        ) : (
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
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

          {/* Template Code (Create only) */}
          {!isEditMode && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Template Code <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={templateCode}
                onChange={(e) => setTemplateCode(e.target.value.toUpperCase())}
                placeholder="e.g., PSYCHIATRY_CORE"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                required
                pattern="[A-Z_]+"
                title="Only uppercase letters and underscores"
              />
              <p className="text-xs text-gray-500 mt-1">
                Unique identifier (uppercase letters and underscores only)
              </p>
            </div>
          )}

          {/* Template Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Template Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              placeholder="e.g., Psychiatry Standard - Core Only"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
              required
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description <span className="text-red-500">*</span>
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe what this template is optimized for..."
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
              required
            />
          </div>

          {/* Two-column layout for specialty and use case */}
          <div className="grid grid-cols-2 gap-4">
            {/* Specialty */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Specialty
              </label>
              <input
                type="text"
                value={specialization}
                onChange={(e) => setSpecialization(e.target.value)}
                placeholder="e.g., psychiatry"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
              />
              <p className="text-xs text-gray-500 mt-1">
                Leave empty to share with all specializations. Specify to restrict visibility.
              </p>
            </div>

            {/* Use Case */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Use Case
              </label>
              <select
                value={useCase}
                onChange={(e) => setUseCase(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
              >
                <option value="">Select use case</option>
                <option value="quick_consultation">Quick Session</option>
                <option value="detailed_review">Detailed Review</option>
                <option value="follow_up">Follow-up</option>
                <option value="emergency">Emergency</option>
                <option value="specialist_referral">Specialist Referral</option>
              </select>
            </div>
          </div>

          {/* Estimated Extraction Time */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Estimated Extraction Time (seconds)
            </label>
            <input
              type="number"
              value={estimatedTime}
              onChange={(e) => setEstimatedTime(e.target.value)}
              placeholder="e.g., 35.5"
              step="0.1"
              min="0"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
            />
            <p className="text-xs text-gray-500 mt-1">
              Performance hint for UI display
            </p>
          </div>

          {/* Inherit Configuration (Create only) */}
          {!isEditMode && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-900 mb-2">
                  Inherit Segment Configuration From
                </label>
                <select
                  value={inheritFromType}
                  onChange={(e) => {
                    const newType = e.target.value as 'none' | 'consultation_type' | 'template';
                    setInheritFromType(newType);
                    // Reset inherit_from_id when changing type
                    if (newType === 'consultation_type') {
                      setInheritFromId(consultationTypeCode);
                    } else if (newType === 'template' && availableTemplates.length > 0) {
                      setInheritFromId(availableTemplates[0].template_code);
                    } else {
                      setInheritFromId('');
                    }
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-900"
                >
                  <option value="none">Configure segments manually</option>
                  <option value="consultation_type">Inherit from Session Type</option>
                  <option value="template">Inherit from Existing Template</option>
                </select>
              </div>

              {/* Show dropdown for selecting consultation type */}
              {inheritFromType === 'consultation_type' && (
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-2">
                    Select Session Type
                  </label>
                  <select
                    value={inheritFromId}
                    onChange={(e) => setInheritFromId(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-900"
                    disabled={loadingOptions}
                  >
                    {consultationTypes.map((type) => (
                      <option key={type.type_code} value={type.type_code}>
                        {type.type_name} ({type.type_code})
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-gray-600 mt-2">
                    Copy all segment definitions from the selected session type's base configuration.
                  </p>
                </div>
              )}

              {/* Show dropdown for selecting template */}
              {inheritFromType === 'template' && (
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-2">
                    Select Template
                  </label>
                  {loadingOptions ? (
                    <div className="text-sm text-gray-600">Loading templates...</div>
                  ) : availableTemplates.length > 0 ? (
                    <>
                      <select
                        value={inheritFromId}
                        onChange={(e) => setInheritFromId(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-900"
                      >
                        {availableTemplates.map((tmpl) => (
                          <option key={tmpl.template_code} value={tmpl.template_code}>
                            {tmpl.template_name} ({tmpl.template_code})
                          </option>
                        ))}
                      </select>
                      <p className="text-xs text-gray-600 mt-2">
                        Copy all segment configurations from the selected template.
                      </p>
                    </>
                  ) : (
                    <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
                      <p className="text-xs text-yellow-800">
                        No templates available to inherit from. Create segments manually or inherit from session type.
                      </p>
                    </div>
                  )}
                </div>
              )}

              {inheritFromType === 'none' && (
                <div className="bg-gray-50 border border-gray-200 rounded p-3">
                  <p className="text-xs text-gray-700">
                    Template will be created without segment configuration. You can configure segments manually after creation using the "Configure Segments" button.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Active Status (Create only) */}
          {!isEditMode && (
            <div className="flex items-center gap-3 py-2">
              <input
                type="checkbox"
                id="is_active"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
              />
              <label htmlFor="is_active" className="text-sm text-gray-700">
                <span className="font-medium">Make template active</span>
                <span className="text-gray-500 ml-1">
                  (inactive templates are hidden from counsellors until activated)
                </span>
              </label>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium transition-colors"
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting
                ? isEditMode
                  ? 'Updating...'
                  : 'Creating...'
                : isEditMode
                ? 'Update Template'
                : 'Create Template'}
            </button>
          </div>
        </form>
        )}
      </div>
    </div>
  );
}
