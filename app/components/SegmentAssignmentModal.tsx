'use client';

import React, { useState, useEffect } from 'react';
import {
  getConsultationTypes,
  assignSegmentToConsultationType,
  unassignSegmentFromConsultationType,
  unassignSegmentFromTemplate,
  handleApiError,
} from '@lib/summaryApi';
import { useAuth } from '@lib/auth';

interface SegmentAssignmentModalProps {
  segment: any;
  isOpen: boolean;
  onClose: () => void;
  onAssignmentChange?: () => void;
}

export function SegmentAssignmentModal({
  segment,
  isOpen,
  onClose,
  onAssignmentChange,
}: SegmentAssignmentModalProps) {
  const { getAccessToken } = useAuth();
  const [showAssignForm, setShowAssignForm] = useState(false);
  const [allConsultationTypes, setAllConsultationTypes] = useState<any[]>([]);
  const [selectedType, setSelectedType] = useState<string>('');
  const [category, setCategory] = useState<string>('additional');
  const [assigning, setAssigning] = useState(false);
  const [unassigning, setUnassigning] = useState<string | null>(null); // Tracks which item is being unassigned
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Load all consultation types when form is shown
  useEffect(() => {
    if (showAssignForm && allConsultationTypes.length === 0) {
      loadConsultationTypes();
    }
  }, [showAssignForm]);

  const loadConsultationTypes = async () => {
    try {
      const response = await getConsultationTypes(getAccessToken());
      if (response.success) {
        setAllConsultationTypes(response.consultation_types);
      }
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handleAssign = async () => {
    if (!selectedType) return;

    setAssigning(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const result = await assignSegmentToConsultationType(
        selectedType,
        segment.segment_code,
        {
          segment_id: segment.id,  // Pass segment ID to avoid ambiguity when segment_code is not unique
          category
        },
        getAccessToken()
      );

      setSuccessMessage(
        `Assigned to ${selectedType}. ${result.templates_synced} template(s) synced.`
      );
      setSelectedType('');
      setShowAssignForm(false);

      // Notify parent to refresh
      if (onAssignmentChange) {
        onAssignmentChange();
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setAssigning(false);
    }
  };

  const handleUnassignFromConsultationType = async (typeCode: string) => {
    if (!confirm(`Are you sure you want to unassign "${segment.segment_code}" from consultation type "${typeCode}"?`)) {
      return;
    }

    setUnassigning(`ct:${typeCode}`);
    setError(null);
    setSuccessMessage(null);

    try {
      await unassignSegmentFromConsultationType(typeCode, segment.segment_code, getAccessToken());
      setSuccessMessage(`Unassigned from ${typeCode} successfully.`);

      // Notify parent to refresh
      if (onAssignmentChange) {
        onAssignmentChange();
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setUnassigning(null);
    }
  };

  const handleUnassignFromTemplate = async (templateCode: string) => {
    if (!confirm(`Are you sure you want to unassign "${segment.segment_code}" from template "${templateCode}"?`)) {
      return;
    }

    setUnassigning(`tpl:${templateCode}`);
    setError(null);
    setSuccessMessage(null);

    try {
      await unassignSegmentFromTemplate(templateCode, segment.segment_code, getAccessToken());
      setSuccessMessage(`Unassigned from template ${templateCode} successfully.`);

      // Notify parent to refresh
      if (onAssignmentChange) {
        onAssignmentChange();
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setUnassigning(null);
    }
  };

  if (!isOpen) return null;

  const hasConsultationTypes = segment.consultation_types && segment.consultation_types.length > 0;
  const hasTemplates = segment.templates && segment.templates.length > 0;
  const hasAssignments = hasConsultationTypes || hasTemplates;

  // Get consultation types this segment is NOT assigned to
  const assignedTypeCodes = new Set(
    (segment.consultation_types || []).map((ct: any) => ct.type_code)
  );
  const unassignedTypes = allConsultationTypes.filter(
    (ct) => !assignedTypeCodes.has(ct.type_code)
  );

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
      <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="border-b border-gray-200 px-6 py-4 flex items-center justify-between sticky top-0 bg-white">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Segment Assignments</h2>
            <p className="text-sm text-gray-600 mt-1">
              {segment.segment_name} ({segment.segment_code})
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Success/Error Messages */}
          {successMessage && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-3">
              <p className="text-sm text-green-800">{successMessage}</p>
            </div>
          )}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          {/* Add Assignment Button/Form */}
          {!showAssignForm ? (
            <button
              onClick={() => setShowAssignForm(true)}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
              </svg>
              Assign to Consultation Type
            </button>
          ) : (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-medium text-green-900">Assign to Consultation Type</h3>
                <button
                  onClick={() => {
                    setShowAssignForm(false);
                    setError(null);
                  }}
                  className="text-green-700 hover:text-green-900"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              {unassignedTypes.length === 0 ? (
                <p className="text-sm text-green-800">
                  This segment is already assigned to all consultation types.
                </p>
              ) : (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Consultation Type
                    </label>
                    <select
                      value={selectedType}
                      onChange={(e) => setSelectedType(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white focus:ring-2 focus:ring-green-500 focus:border-green-500"
                    >
                      <option value="">Select consultation type...</option>
                      {unassignedTypes.map((ct) => (
                        <option key={ct.type_code} value={ct.type_code}>
                          {ct.type_name} ({ct.type_code})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Default Category
                    </label>
                    <select
                      value={category}
                      onChange={(e) => setCategory(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white focus:ring-2 focus:ring-green-500 focus:border-green-500"
                    >
                      <option value="core">Core</option>
                      <option value="additional">Additional</option>
                      <option value="excluded">Excluded</option>
                    </select>
                    <p className="text-xs text-gray-500 mt-1">
                      Templates will receive this segment as &quot;excluded&quot; (auto-sync)
                    </p>
                  </div>

                  <button
                    onClick={handleAssign}
                    disabled={!selectedType || assigning}
                    className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {assigning ? 'Assigning...' : 'Assign Segment'}
                  </button>
                </>
              )}
            </div>
          )}

          {!hasAssignments ? (
            <div className="text-center py-8 text-gray-500">
              <svg className="w-16 h-16 mx-auto text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
              </svg>
              <p className="text-lg font-medium">No Assignments Yet</p>
              <p className="text-sm mt-2">Use the button above to assign this segment to consultation types.</p>
            </div>
          ) : (
            <>
              {/* Consultation Types Section */}
              {hasConsultationTypes && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
                    <span className="w-2 h-2 bg-purple-500 rounded-full"></span>
                    Consultation Types ({segment.consultation_types.length})
                  </h3>
                  <div className="grid gap-3">
                    {segment.consultation_types.map((ct: any) => (
                      <div
                        key={ct.type_code}
                        className="bg-purple-50 border border-purple-200 rounded-lg p-4 hover:shadow-sm transition-shadow"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="px-2 py-1 bg-purple-600 text-white rounded text-xs font-bold">
                                {ct.type_code}
                              </span>
                              <span className="font-medium text-gray-900">{ct.type_name}</span>
                            </div>
                            {ct.description && (
                              <p className="text-sm text-gray-600 mt-2">{ct.description}</p>
                            )}
                          </div>
                          <button
                            onClick={() => handleUnassignFromConsultationType(ct.type_code)}
                            disabled={unassigning === `ct:${ct.type_code}`}
                            className="ml-3 px-3 py-1.5 text-xs font-medium text-red-600 hover:text-red-700 hover:bg-red-50 border border-red-200 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            title={`Unassign from ${ct.type_name}`}
                          >
                            {unassigning === `ct:${ct.type_code}` ? (
                              <span className="flex items-center gap-1">
                                <svg className="animate-spin h-3 w-3" fill="none" viewBox="0 0 24 24">
                                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Removing...
                              </span>
                            ) : (
                              'Unassign'
                            )}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Templates Section */}
              {hasTemplates && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
                    <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
                    Templates ({segment.templates.length})
                  </h3>
                  <div className="grid gap-3">
                    {segment.templates.map((tpl: any) => (
                      <div
                        key={tpl.template_code}
                        className="bg-blue-50 border border-blue-200 rounded-lg p-4 hover:shadow-sm transition-shadow"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="px-2 py-1 bg-blue-600 text-white rounded text-xs font-bold">
                                {tpl.template_code}
                              </span>
                              <span className="font-medium text-gray-900">
                                {tpl.template_name || tpl.template_code}
                              </span>
                            </div>
                            {tpl.description && (
                              <p className="text-sm text-gray-600 mt-2">{tpl.description}</p>
                            )}
                            {tpl.use_case && (
                              <div className="flex items-center gap-2 mt-2">
                                <span className="text-xs text-gray-500">Use Case:</span>
                                <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded">
                                  {tpl.use_case}
                                </span>
                              </div>
                            )}
                          </div>
                          <button
                            onClick={() => handleUnassignFromTemplate(tpl.template_code)}
                            disabled={unassigning === `tpl:${tpl.template_code}`}
                            className="ml-3 px-3 py-1.5 text-xs font-medium text-red-600 hover:text-red-700 hover:bg-red-50 border border-red-200 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            title={`Unassign from ${tpl.template_name || tpl.template_code}`}
                          >
                            {unassigning === `tpl:${tpl.template_code}` ? (
                              <span className="flex items-center gap-1">
                                <svg className="animate-spin h-3 w-3" fill="none" viewBox="0 0 24 24">
                                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Removing...
                              </span>
                            ) : (
                              'Unassign'
                            )}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 px-6 py-4 bg-gray-50">
          <button
            onClick={onClose}
            className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
