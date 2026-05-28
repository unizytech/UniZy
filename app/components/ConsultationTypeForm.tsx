'use client';

import React, { useState, useEffect } from 'react';
import {
  createConsultationType,
  handleApiError,
  type CreateConsultationTypeRequest,
  getConsultationTypes,
} from '@lib/summaryApi';
import { useAuth } from '@lib/auth';

interface ConsultationTypeFormProps {
  onSuccess: () => void;
  onCancel: () => void;
}

type CreationMode = 'scratch' | 'clone';

export function ConsultationTypeForm({
  onSuccess,
  onCancel,
}: ConsultationTypeFormProps) {
  const { getAccessToken } = useAuth();

  // Creation mode
  const [creationMode, setCreationMode] = useState<CreationMode>('scratch');
  const [sourceConsultationTypeId, setSourceConsultationTypeId] = useState('');
  const [availableConsultationTypes, setAvailableConsultationTypes] = useState<any[]>([]);

  // Form state
  const [typeCode, setTypeCode] = useState('');
  const [typeName, setTypeName] = useState('');
  const [description, setDescription] = useState('');
  const [specialtyApplicable, setSpecialtyApplicable] = useState('');
  const [displayOrder, setDisplayOrder] = useState('10');
  const [iconName, setIconName] = useState('');
  const [colorCode, setColorCode] = useState('#4F46E5');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load available consultation types for cloning (runs once on mount)
  useEffect(() => {
    const loadConsultationTypes = async () => {
      try {
        const response = await getConsultationTypes(getAccessToken());
        if (response.success) {
          setAvailableConsultationTypes(response.consultation_types);
        }
      } catch (err) {
        console.error('Failed to load consultation types:', err);
      }
    };
    loadConsultationTypes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run once on mount - getAccessToken is stable from useAuth

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      // Validate clone mode
      if (creationMode === 'clone' && !sourceConsultationTypeId) {
        setError('Please select a consultation type to clone from');
        setSubmitting(false);
        return;
      }

      // Parse specialty_applicable from comma-separated string
      const specialties = specialtyApplicable
        .split(',')
        .map(s => s.trim())
        .filter(s => s.length > 0);

      const createData: CreateConsultationTypeRequest = {
        type_code: typeCode.trim().toUpperCase(),
        type_name: typeName.trim(),
        description: description || undefined,
        specialty_applicable: specialties.length > 0 ? specialties : undefined,
        display_order: parseInt(displayOrder),
        icon_name: iconName || undefined,
        color_code: colorCode || undefined,
        clone_from_consultation_type_id: creationMode === 'clone' ? sourceConsultationTypeId : undefined,
        // Default visibility: all doctors, hospitals, and specializations can see it
        // (no visibility restrictions on creation - can be edited later)
      };

      await createConsultationType(createData, getAccessToken());
      onSuccess();
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-4">
      <div className="bg-white rounded-lg shadow-xl max-w-5xl w-full max-h-[95vh] overflow-y-auto">
        {/* Header */}
        <div className="bg-blue-600 text-white p-6 rounded-t-lg">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-2xl font-bold">Create New Consultation Type</h2>
              <p className="text-blue-100 text-sm mt-1">
                Define a new consultation type with common segments
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onCancel}
                disabled={submitting}
                className="px-4 py-2 bg-white text-blue-600 hover:bg-blue-50 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                onClick={handleSubmit}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {submitting && (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                )}
                {submitting ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>

        {/* Form */}
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

          {/* Creation Mode Selector */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Creation Method
            </label>
            <div className="flex gap-4">
              <button
                type="button"
                onClick={() => setCreationMode('scratch')}
                className={`flex-1 px-4 py-3 rounded-lg border-2 text-sm font-medium transition-all ${
                  creationMode === 'scratch'
                    ? 'border-blue-600 bg-blue-600 text-white shadow-md'
                    : 'border-gray-300 bg-white text-gray-700 hover:border-blue-400'
                }`}
              >
                <div className="text-center">
                  <div className="text-lg mb-1">📝</div>
                  <div className="font-semibold">From Scratch</div>
                  <div className="text-xs opacity-90 mt-1">
                    {creationMode === 'scratch' ? 'No default segments' : 'Start empty'}
                  </div>
                </div>
              </button>
              <button
                type="button"
                onClick={() => setCreationMode('clone')}
                className={`flex-1 px-4 py-3 rounded-lg border-2 text-sm font-medium transition-all ${
                  creationMode === 'clone'
                    ? 'border-green-600 bg-green-600 text-white shadow-md'
                    : 'border-gray-300 bg-white text-gray-700 hover:border-green-400'
                }`}
              >
                <div className="text-center">
                  <div className="text-lg mb-1">📋</div>
                  <div className="font-semibold">Clone Existing</div>
                  <div className="text-xs opacity-90 mt-1">
                    {creationMode === 'clone' ? 'Copy segments & config' : 'Faster setup'}
                  </div>
                </div>
              </button>
            </div>

            {/* Clone Source Selector */}
            {creationMode === 'clone' && (
              <div className="mt-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Clone From <span className="text-red-500">*</span>
                </label>
                <select
                  value={sourceConsultationTypeId}
                  onChange={(e) => setSourceConsultationTypeId(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500 text-gray-900 bg-white"
                  required={creationMode === 'clone'}
                >
                  <option value="">Select consultation type to clone...</option>
                  {availableConsultationTypes.map((ct) => (
                    <option key={ct.id} value={ct.id}>
                      {ct.type_name} ({ct.type_code})
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  All segments and configurations will be copied to the new consultation type
                </p>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* Type Code */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Type Code <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={typeCode}
                onChange={(e) => setTypeCode(e.target.value.toUpperCase())}
                required
                placeholder="e.g., EMERGENCY"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm text-gray-900"
              />
              <p className="text-xs text-gray-500 mt-1">
                Unique identifier (uppercase, underscores)
              </p>
            </div>

            {/* Type Name */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Type Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={typeName}
                onChange={(e) => setTypeName(e.target.value)}
                required
                placeholder="e.g., Emergency Consultation"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900"
              />
              <p className="text-xs text-gray-500 mt-1">
                Display name for the consultation type
              </p>
            </div>

            {/* Display Order */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Display Order <span className="text-red-500">*</span>
              </label>
              <input
                type="number"
                value={displayOrder}
                onChange={(e) => setDisplayOrder(e.target.value)}
                required
                min={1}
                max={100}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900"
              />
              <p className="text-xs text-gray-500 mt-1">
                Order in which types are displayed (1-100)
              </p>
            </div>

            {/* Color Code */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Color Code
              </label>
              <div className="flex gap-2">
                <input
                  type="color"
                  value={colorCode}
                  onChange={(e) => setColorCode(e.target.value)}
                  className="h-10 w-16 border border-gray-300 rounded-lg cursor-pointer"
                />
                <input
                  type="text"
                  value={colorCode}
                  onChange={(e) => setColorCode(e.target.value)}
                  placeholder="#4F46E5"
                  className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm text-gray-900"
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">
                UI color theme for this type
              </p>
            </div>

            {/* Icon Name */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Icon Name
              </label>
              <input
                type="text"
                value={iconName}
                onChange={(e) => setIconName(e.target.value)}
                placeholder="e.g., emergency, hospital"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900"
              />
              <p className="text-xs text-gray-500 mt-1">
                Icon name for UI display (optional)
              </p>
            </div>

            {/* Specialty Applicable */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Applicable Specialties
              </label>
              <input
                type="text"
                value={specialtyApplicable}
                onChange={(e) => setSpecialtyApplicable(e.target.value)}
                placeholder="e.g., emergency_medicine, general_medicine"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900"
              />
              <p className="text-xs text-gray-500 mt-1">
                Comma-separated list of specialties
              </p>
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              placeholder="Detailed description of this consultation type..."
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900"
            />
            <p className="text-xs text-gray-500 mt-1">
              Optional description explaining when to use this type
            </p>
          </div>

          {/* Visibility Info Box */}
          <div className="bg-green-50 border border-green-200 rounded-lg p-3">
            <div className="flex items-start">
              <svg
                className="w-5 h-5 text-green-600 mr-2 mt-0.5 flex-shrink-0"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                  clipRule="evenodd"
                />
              </svg>
              <div>
                <p className="text-sm font-semibold text-green-900">Default Visibility</p>
                <p className="text-sm text-green-800 mt-1">
                  This consultation type will be visible to <strong>all doctors, hospitals, and specializations</strong> by default. You can edit visibility settings after creation using the "Edit Visibility" button.
                </p>
              </div>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
