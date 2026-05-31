'use client';

import React, { useState, useEffect } from 'react';
import {
  getAllDoctorsForSharing,
  getHospitals,
  getSpecializations,
  DoctorListItem,
  Hospital
} from "@/services/doctorApi";
import { handleApiError } from "@lib/summaryApi";
import { useAuth } from '@lib/auth';
import { authPatch } from '@lib/apiClient';

interface EditConsultationTypeVisibilityModalProps {
  consultationType: any;
  isOpen: boolean;
  onClose: () => void;
  onSaveComplete?: () => void;
}

type VisibilityTab = 'doctors' | 'hospitals' | 'specializations';

export function EditConsultationTypeVisibilityModal({
  consultationType,
  isOpen,
  onClose,
  onSaveComplete
}: EditConsultationTypeVisibilityModalProps) {
  const { getAccessToken } = useAuth();
  const [activeTab, setActiveTab] = useState<VisibilityTab>('doctors');
  const [selectedDoctors, setSelectedDoctors] = useState<string[]>([]);
  const [selectedHospitals, setSelectedHospitals] = useState<string[]>([]);
  const [selectedSpecializations, setSelectedSpecializations] = useState<string[]>([]);
  const [visibleToAll, setVisibleToAll] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Data fetching states
  const [doctors, setDoctors] = useState<DoctorListItem[]>([]);
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [specializations, setSpecializations] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Fetch data on mount
  useEffect(() => {
    if (isOpen) {
      fetchData();
      loadCurrentVisibility();
    }
  }, [isOpen]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const token = getAccessToken();
      const [doctorsData, hospitalsData, specializationsData] = await Promise.all([
        getAllDoctorsForSharing(token),
        getHospitals(token),
        getSpecializations(token)
      ]);
      setDoctors(doctorsData);
      setHospitals(hospitalsData);
      setSpecializations(specializationsData);
    } catch (err) {
      setError('Failed to load data: ' + (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const loadCurrentVisibility = () => {
    // Check if consultation type has restricted visibility
    const hasRestrictions =
      (consultationType.visible_to_doctors && consultationType.visible_to_doctors.length > 0) ||
      (consultationType.visible_to_hospitals && consultationType.visible_to_hospitals.length > 0) ||
      (consultationType.visible_to_specializations && consultationType.visible_to_specializations.length > 0);

    setVisibleToAll(!hasRestrictions);

    if (hasRestrictions) {
      setSelectedDoctors(consultationType.visible_to_doctors || []);
      setSelectedHospitals(consultationType.visible_to_hospitals || []);
      setSelectedSpecializations(consultationType.visible_to_specializations || []);
    } else {
      setSelectedDoctors([]);
      setSelectedHospitals([]);
      setSelectedSpecializations([]);
    }
  };

  if (!isOpen) return null;

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      // Prepare payload
      const payload = visibleToAll ? {
        visible_to_all: true,
        visible_to_doctors: [],
        visible_to_hospitals: [],
        visible_to_specializations: []
      } : {
        visible_to_all: false,
        visible_to_doctors: selectedDoctors,
        visible_to_hospitals: selectedHospitals,
        visible_to_specializations: selectedSpecializations
      };

      const response = await authPatch(
        `/api/v1/summary/admin/consultation-types/${consultationType.type_code}/visibility`,
        getAccessToken(),
        payload
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to update visibility');
      }

      setSuccess('Visibility updated successfully');

      // Call completion callback
      if (onSaveComplete) {
        setTimeout(() => {
          onSaveComplete();
        }, 1000);
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => {
    setError(null);
    setSuccess(null);
    setSearchQuery('');
    onClose();
  };

  const toggleDoctor = (doctorId: string) => {
    setSelectedDoctors(prev =>
      prev.includes(doctorId)
        ? prev.filter(id => id !== doctorId)
        : [...prev, doctorId]
    );
  };

  const toggleHospital = (hospitalId: string) => {
    setSelectedHospitals(prev =>
      prev.includes(hospitalId)
        ? prev.filter(id => id !== hospitalId)
        : [...prev, hospitalId]
    );
  };

  const toggleSpecialization = (spec: string) => {
    setSelectedSpecializations(prev =>
      prev.includes(spec)
        ? prev.filter(s => s !== spec)
        : [...prev, spec]
    );
  };

  // Filter doctors based on search query
  const filteredDoctors = doctors.filter(doc =>
    doc.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    doc.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (doc.specialization && doc.specialization.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
      <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="border-b border-gray-200 px-6 py-4 flex items-center justify-between sticky top-0 bg-white">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Edit Visibility</h2>
            <p className="text-sm text-gray-600 mt-1">
              {consultationType?.type_name} ({consultationType?.type_code})
            </p>
          </div>
          <button
            onClick={handleClose}
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
          {/* Error/Success Messages */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="flex items-center">
                <svg className="w-5 h-5 text-red-600 mr-2" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                    clipRule="evenodd"
                  />
                </svg>
                <p className="text-red-800 text-sm">{error}</p>
              </div>
            </div>
          )}

          {success && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <div className="flex items-center">
                <svg className="w-5 h-5 text-green-600 mr-2" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                    clipRule="evenodd"
                  />
                </svg>
                <p className="text-green-800 text-sm">{success}</p>
              </div>
            </div>
          )}

          {/* Visibility Mode Toggle */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <input
                type="checkbox"
                id="visibleToAll"
                checked={visibleToAll}
                onChange={(e) => setVisibleToAll(e.target.checked)}
                className="w-5 h-5 text-blue-600 focus:ring-blue-500 rounded mt-0.5"
              />
              <div className="flex-1">
                <label htmlFor="visibleToAll" className="font-medium text-sm text-gray-900 cursor-pointer">
                  Visible to All Counsellors, Schools & Specializations
                </label>
                <p className="text-xs text-gray-600 mt-1">
                  When checked, this session type will be available to everyone. Uncheck to restrict visibility to specific entities.
                </p>
              </div>
            </div>
          </div>

          {/* Tabs (only show if not visible to all) */}
          {!visibleToAll && !loading && (
            <>
              <div className="border-b border-gray-200">
                <nav className="flex space-x-8">
                  <button
                    onClick={() => setActiveTab('doctors')}
                    className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                      activeTab === 'doctors'
                        ? 'border-blue-500 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }`}
                  >
                    👨‍⚕️ Counsellors ({selectedDoctors.length})
                  </button>
                  <button
                    onClick={() => setActiveTab('hospitals')}
                    className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                      activeTab === 'hospitals'
                        ? 'border-blue-500 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }`}
                  >
                    🏥 Schools ({selectedHospitals.length})
                  </button>
                  <button
                    onClick={() => setActiveTab('specializations')}
                    className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                      activeTab === 'specializations'
                        ? 'border-blue-500 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }`}
                  >
                    🩺 Specializations ({selectedSpecializations.length})
                  </button>
                </nav>
              </div>

              {/* Tab Content */}
              <div className="space-y-4">
                {activeTab === 'doctors' && (
                  <div className="space-y-4">
                    {/* Search Bar */}
                    <div>
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search counsellors by name, email, or specialization..."
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                      />
                    </div>

                    {/* Doctors List */}
                    <div className="max-h-96 overflow-y-auto border border-gray-200 rounded-lg">
                      {filteredDoctors.length === 0 ? (
                        <div className="text-center py-8 text-gray-500">
                          {searchQuery ? 'No counsellors found matching your search.' : 'No counsellors available.'}
                        </div>
                      ) : (
                        <div className="divide-y divide-gray-200">
                          {filteredDoctors.map((doctor) => (
                            <label
                              key={doctor.id}
                              className="flex items-center p-3 hover:bg-gray-50 cursor-pointer"
                            >
                              <input
                                type="checkbox"
                                checked={selectedDoctors.includes(doctor.id)}
                                onChange={() => toggleDoctor(doctor.id)}
                                className="w-4 h-4 text-blue-600 focus:ring-blue-500 rounded"
                              />
                              <div className="ml-3 flex-1">
                                <div className="font-medium text-sm text-gray-900">{doctor.full_name}</div>
                                <div className="text-xs text-gray-500">
                                  {doctor.email}
                                  {doctor.specialization && ` • ${doctor.specialization}`}
                                </div>
                              </div>
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {activeTab === 'hospitals' && (
                  <div className="space-y-4">
                    {/* Hospitals List */}
                    <div className="max-h-96 overflow-y-auto border border-gray-200 rounded-lg">
                      {hospitals.length === 0 ? (
                        <div className="text-center py-8 text-gray-500">No schools available.</div>
                      ) : (
                        <div className="divide-y divide-gray-200">
                          {hospitals.map((hospital) => (
                            <label
                              key={hospital.id}
                              className="flex items-center p-3 hover:bg-gray-50 cursor-pointer"
                            >
                              <input
                                type="checkbox"
                                checked={selectedHospitals.includes(hospital.id)}
                                onChange={() => toggleHospital(hospital.id)}
                                className="w-4 h-4 text-blue-600 focus:ring-blue-500 rounded"
                              />
                              <div className="ml-3 flex-1">
                                <div className="font-medium text-sm text-gray-900">{hospital.hospital_name}</div>
                                <div className="text-xs text-gray-500">
                                  {hospital.city && hospital.state
                                    ? `${hospital.city}, ${hospital.state}`
                                    : hospital.city || hospital.state || 'Location not specified'}
                                </div>
                              </div>
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {activeTab === 'specializations' && (
                  <div className="space-y-4">
                    {/* Specializations List */}
                    <div className="max-h-96 overflow-y-auto border border-gray-200 rounded-lg">
                      {specializations.length === 0 ? (
                        <div className="text-center py-8 text-gray-500">No specializations available.</div>
                      ) : (
                        <div className="divide-y divide-gray-200">
                          {specializations.map((spec) => (
                            <label
                              key={spec}
                              className="flex items-center p-3 hover:bg-gray-50 cursor-pointer"
                            >
                              <input
                                type="checkbox"
                                checked={selectedSpecializations.includes(spec)}
                                onChange={() => toggleSpecialization(spec)}
                                className="w-4 h-4 text-blue-600 focus:ring-blue-500 rounded"
                              />
                              <div className="ml-3 flex-1">
                                <div className="font-medium text-sm text-gray-900">{spec}</div>
                              </div>
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {/* Loading State */}
          {loading && (
            <div className="flex items-center justify-center py-8">
              <svg className="animate-spin h-8 w-8 text-blue-600" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 px-6 py-4 flex items-center justify-end space-x-3 bg-gray-50">
          <button
            onClick={handleClose}
            className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || loading}
            className={`px-4 py-2 rounded-lg font-medium transition-all ${
              saving || loading
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm hover:shadow'
            }`}
          >
            {saving ? (
              <span className="flex items-center">
                <svg
                  className="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  ></circle>
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  ></path>
                </svg>
                Saving...
              </span>
            ) : (
              'Save Changes'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
