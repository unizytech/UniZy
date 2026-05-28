'use client';

import React, { useState, useEffect } from 'react';
import {
  shareTemplate,
  shareTemplateWithHospital,
  shareTemplateWithSpecialization,
  revokeTemplateAccess,
  getTemplateShares,
  handleApiError
} from "@lib/summaryApi";
import {
  getAllDoctorsForSharing,
  getHospitals,
  getSpecializations,
  DoctorListItem,
  Hospital
} from "@/services/doctorApi";
import {
  getAllNursesForSharing,
  shareTemplateWithNurses,
  getTemplateNurseShares,
  revokeNurseTemplateAccess,
  type NurseListItem
} from "@/services/nurseApi";
import { useAuth } from '@lib/auth';

interface ShareTemplateModalProps {
  template: any;
  isOpen: boolean;
  onClose: () => void;
  onShareComplete?: () => void;
}

type ShareTab = 'individual' | 'hospital' | 'specialization' | 'nurses';

export function ShareTemplateModal({
  template,
  isOpen,
  onClose,
  onShareComplete
}: ShareTemplateModalProps) {
  const { getAccessToken } = useAuth();
  const [activeTab, setActiveTab] = useState<ShareTab>('individual');
  const [selectedDoctors, setSelectedDoctors] = useState<string[]>([]);
  const [selectedHospitals, setSelectedHospitals] = useState<string[]>([]);
  const [selectedSpecializations, setSelectedSpecializations] = useState<string[]>([]);
  // accessLevel removed — all shares are now 'use'
  const [sharing, setSharing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [sharedDoctors, setSharedDoctors] = useState<any[]>([]);

  // Owner selection for global templates
  const [selectedOwner, setSelectedOwner] = useState<string>('');
  const isGlobalTemplate = !template?.doctor_id;

  // Track initial state for comparison (to detect adds/removes)
  const [initialHospitalIds, setInitialHospitalIds] = useState<string[]>([]);
  const [initialSpecializations, setInitialSpecializations] = useState<string[]>([]);

  // Data fetching states
  const [doctors, setDoctors] = useState<DoctorListItem[]>([]);
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [specializations, setSpecializations] = useState<string[]>([]);
  const [nurses, setNurses] = useState<NurseListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [nurseSearchQuery, setNurseSearchQuery] = useState('');

  // Nurse selection state
  const [selectedNurses, setSelectedNurses] = useState<string[]>([]);
  const [sharedNurses, setSharedNurses] = useState<Array<{ nurse_id: string; is_active: boolean }>>([]);
  const [initialNurseIds, setInitialNurseIds] = useState<string[]>([]);

  // Fetch data on mount
  useEffect(() => {
    if (isOpen) {
      fetchData();
    }
  }, [isOpen]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const token = getAccessToken();
      const [doctorsData, hospitalsData, specializationsData, sharesData, nursesData, nurseSharesData] = await Promise.all([
        getAllDoctorsForSharing(token),
        getHospitals(token),
        getSpecializations(token),
        getTemplateShares(template.id, token),
        getAllNursesForSharing(token),
        getTemplateNurseShares(template.id, token)
      ]);

      setDoctors(doctorsData);
      setHospitals(hospitalsData);
      setSpecializations(specializationsData);
      setNurses(nursesData);

      // Set existing doctor shares
      if (sharesData.success) {
        setSharedDoctors(sharesData.shares.doctors);

        // Pre-select existing shares
        setSelectedDoctors(sharesData.shares.doctors.map(d => d.doctor_id));
        setSelectedHospitals(sharesData.shares.hospital_ids);
        setSelectedSpecializations(sharesData.shares.specializations);

        // Store initial state for comparison when saving
        setInitialHospitalIds(sharesData.shares.hospital_ids);
        setInitialSpecializations(sharesData.shares.specializations);
      }

      // Set existing nurse shares
      if (nurseSharesData && nurseSharesData.length > 0) {
        setSharedNurses(nurseSharesData);
        setSelectedNurses(nurseSharesData.map(s => s.nurse_id));
        setInitialNurseIds(nurseSharesData.map(s => s.nurse_id));
      }
    } catch (err) {
      setError('Failed to load data: ' + (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  const handleShare = async () => {
    try {
      setSharing(true);
      setError(null);
      setSuccess(null);

      // Validate owner selection for global templates (only for doctor tabs, not nurses)
      if (isGlobalTemplate && !selectedOwner && activeTab !== 'nurses') {
        setError('Please select a template owner before sharing. This will convert the global template to a doctor-owned template.');
        setSharing(false);
        return;
      }

      let totalShared = 0;
      let totalRemoved = 0;
      let ownershipAssigned = false;

      // For global templates, pass the selectedOwner to assign ownership
      const newOwnerId = isGlobalTemplate ? selectedOwner : undefined;

      // Determine who is sharing: existing owner for doctor templates, or selected owner for global templates
      const sharingDoctorId = template.doctor_id || selectedOwner;

      // Each tab operates independently - only process the active tab's selections
      if (activeTab === 'individual') {
        // DOCTORS TAB: Add/remove individual doctor shares
        // Ignore hospitals and specializations state completely
        const existingDoctorIds = sharedDoctors.map(d => d.doctor_id);
        const doctorsToAdd = selectedDoctors.filter(id => !existingDoctorIds.includes(id));
        const doctorsToRemove = existingDoctorIds.filter(id => !selectedDoctors.includes(id));

        // Add new shares (with ownership assignment for global templates)
        const token = getAccessToken();
        if (doctorsToAdd.length > 0) {
          const result = await shareTemplate(sharingDoctorId, template.id, doctorsToAdd, newOwnerId, token);
          totalShared = result.shared_count;
          if (result.ownership_assigned) {
            ownershipAssigned = true;
          }
        } else if (newOwnerId) {
          // Even if no doctors to add, we need to assign ownership
          // Create a share for just the owner
          const result = await shareTemplate(sharingDoctorId, template.id, [newOwnerId], newOwnerId, token);
          if (result.ownership_assigned) {
            ownershipAssigned = true;
          }
        }

        // Remove unchecked shares
        if (doctorsToRemove.length > 0) {
          for (const doctorId of doctorsToRemove) {
            await revokeTemplateAccess(sharingDoctorId, doctorId, template.id, token);
            totalRemoved++;
          }
        }

        if (ownershipAssigned) {
          const ownerName = doctors.find(d => d.id === selectedOwner)?.full_name || 'selected doctor';
          setSuccess(`Template ownership assigned to ${ownerName}. Shared with ${totalShared} doctor(s)${totalRemoved > 0 ? `, removed ${totalRemoved}` : ''}`);
        } else if (totalShared > 0 && totalRemoved > 0) {
          setSuccess(`Updated shares: Added ${totalShared}, removed ${totalRemoved}`);
        } else if (totalShared > 0) {
          setSuccess(`Template shared with ${totalShared} new doctor(s)`);
        } else if (totalRemoved > 0) {
          setSuccess(`Removed ${totalRemoved} doctor share(s)`);
        } else {
          setSuccess('No changes made');
        }

      } else if (activeTab === 'hospital') {
        // HOSPITAL TAB: Add/remove hospital shares
        // Ignore doctors and specializations state completely
        const token = getAccessToken();

        // Determine which hospitals to add and which to remove
        const hospitalsToAdd = selectedHospitals.filter(id => !initialHospitalIds.includes(id));
        const hospitalsToRemove = initialHospitalIds.filter(id => !selectedHospitals.includes(id));

        // Add new hospital shares (pass owner on first share for global templates)
        let ownerPassedOnce = false;
        for (const hospitalId of hospitalsToAdd) {
          const ownerForThisCall = (!ownerPassedOnce && newOwnerId) ? newOwnerId : undefined;
          const result = await shareTemplateWithHospital(sharingDoctorId, template.id, hospitalId, ownerForThisCall, token);
          totalShared += result.shared_count;
          if (result.ownership_assigned) {
            ownershipAssigned = true;
            ownerPassedOnce = true;
          }
        }

        // If no hospitals to add but we need to assign ownership, do it via individual share
        if (hospitalsToAdd.length === 0 && newOwnerId) {
          const result = await shareTemplate(sharingDoctorId, template.id, [newOwnerId], newOwnerId, token);
          if (result.ownership_assigned) {
            ownershipAssigned = true;
          }
        }

        // Remove unchecked hospital shares (revoke from ALL doctors in those hospitals)
        for (const hospitalId of hospitalsToRemove) {
          // Get all doctors in this hospital from the sharedDoctors list
          const doctorsInHospital = sharedDoctors
            .filter(d => d.hospital_id === hospitalId)
            .map(d => d.doctor_id);

          // Revoke access from each doctor
          for (const doctorId of doctorsInHospital) {
            await revokeTemplateAccess(sharingDoctorId, doctorId, template.id, token);
            totalRemoved++;
          }
        }

        if (ownershipAssigned) {
          const ownerName = doctors.find(d => d.id === selectedOwner)?.full_name || 'selected doctor';
          setSuccess(`Template ownership assigned to ${ownerName}. Shared with ${totalShared} doctor(s) across ${hospitalsToAdd.length} hospital(s)`);
        } else if (totalShared > 0 && totalRemoved > 0) {
          setSuccess(`Updated shares: Added ${totalShared}, removed ${totalRemoved}`);
        } else if (totalShared > 0) {
          setSuccess(`Template shared with ${totalShared} doctor(s) across ${hospitalsToAdd.length} hospital(s)`);
        } else if (totalRemoved > 0) {
          setSuccess(`Removed template from ${totalRemoved} doctor(s) in ${hospitalsToRemove.length} hospital(s)`);
        } else {
          setSuccess('No changes made');
        }

      } else if (activeTab === 'specialization') {
        // SPECIALIZATION TAB: Add/remove specialization shares
        // Ignore doctors and hospitals state completely
        const token = getAccessToken();

        // Determine which specializations to add and which to remove
        const specsToAdd = selectedSpecializations.filter(spec => !initialSpecializations.includes(spec));
        const specsToRemove = initialSpecializations.filter(spec => !selectedSpecializations.includes(spec));

        // Add new specialization shares (pass owner on first share for global templates)
        let ownerPassedOnce = false;
        for (const spec of specsToAdd) {
          const ownerForThisCall = (!ownerPassedOnce && newOwnerId) ? newOwnerId : undefined;
          const result = await shareTemplateWithSpecialization(sharingDoctorId, template.id, spec, ownerForThisCall, token);
          totalShared += result.shared_count;
          if (result.ownership_assigned) {
            ownershipAssigned = true;
            ownerPassedOnce = true;
          }
        }

        // If no specializations to add but we need to assign ownership, do it via individual share
        if (specsToAdd.length === 0 && newOwnerId) {
          const result = await shareTemplate(sharingDoctorId, template.id, [newOwnerId], newOwnerId, token);
          if (result.ownership_assigned) {
            ownershipAssigned = true;
          }
        }

        // Remove unchecked specialization shares (revoke from ALL doctors with those specializations)
        for (const spec of specsToRemove) {
          // Get all doctors with this specialization from the sharedDoctors list
          const doctorsWithSpec = sharedDoctors
            .filter(d => d.specialization === spec)
            .map(d => d.doctor_id);

          // Revoke access from each doctor
          for (const doctorId of doctorsWithSpec) {
            await revokeTemplateAccess(sharingDoctorId, doctorId, template.id, token);
            totalRemoved++;
          }
        }

        if (ownershipAssigned) {
          const ownerName = doctors.find(d => d.id === selectedOwner)?.full_name || 'selected doctor';
          setSuccess(`Template ownership assigned to ${ownerName}. Shared with ${totalShared} doctor(s) across ${specsToAdd.length} specialization(s)`);
        } else if (totalShared > 0 && totalRemoved > 0) {
          setSuccess(`Updated shares: Added ${totalShared}, removed ${totalRemoved}`);
        } else if (totalShared > 0) {
          setSuccess(`Template shared with ${totalShared} doctor(s) across ${specsToAdd.length} specialization(s)`);
        } else if (totalRemoved > 0) {
          setSuccess(`Removed template from ${totalRemoved} doctor(s) with ${specsToRemove.length} specialization(s)`);
        } else {
          setSuccess('No changes made');
        }
      } else if (activeTab === 'nurses') {
        // NURSES TAB: Add/remove nurse shares
        // Ignore doctors, hospitals, and specializations state completely

        // Determine which nurses to add and which to remove
        const nursesToAdd = selectedNurses.filter(id => !initialNurseIds.includes(id));
        const nursesToRemove = initialNurseIds.filter(id => !selectedNurses.includes(id));

        // Add new nurse shares
        if (nursesToAdd.length > 0) {
          const result = await shareTemplateWithNurses(
            template.id,
            template.template_code,
            nursesToAdd,
            getAccessToken()
          );
          totalShared = result.shared_count;
        }

        // Remove unchecked nurse shares
        for (const nurseId of nursesToRemove) {
          await revokeNurseTemplateAccess(nurseId, template.id, getAccessToken());
          totalRemoved++;
        }

        if (totalShared > 0 && totalRemoved > 0) {
          setSuccess(`Updated nurse shares: Added ${totalShared}, removed ${totalRemoved}`);
        } else if (totalShared > 0) {
          setSuccess(`Template shared with ${totalShared} nurse(s)`);
        } else if (totalRemoved > 0) {
          setSuccess(`Removed ${totalRemoved} nurse share(s)`);
        } else {
          setSuccess('No changes made');
        }
      }

      // Refresh data to show updated shares
      await fetchData();

      // Call completion callback
      if (onShareComplete) {
        onShareComplete();
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setSharing(false);
    }
  };

  const handleRevoke = async (doctorId: string) => {
    try {
      // The sharing doctor is the template owner
      const sharingDoctorId = template.doctor_id;
      if (!sharingDoctorId) {
        setError('Cannot revoke access from a global template. Please assign an owner first.');
        return;
      }
      const token = getAccessToken();
      await revokeTemplateAccess(sharingDoctorId, doctorId, template.id, token);
      setSuccess('Access revoked successfully');
      // Remove from both sharedDoctors AND selectedDoctors to prevent re-adding on share
      setSharedDoctors(sharedDoctors.filter(d => d.doctor_id !== doctorId));
      setSelectedDoctors(prev => prev.filter(id => id !== doctorId));
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handleClose = () => {
    setError(null);
    setSuccess(null);
    setSelectedDoctors([]);
    setSelectedHospitals([]);
    setSelectedSpecializations([]);
    setSelectedNurses([]);
    setInitialHospitalIds([]);
    setInitialSpecializations([]);
    setInitialNurseIds([]);
    setSearchQuery('');
    setNurseSearchQuery('');
    setSelectedOwner('');
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

  const toggleNurse = (nurseId: string) => {
    setSelectedNurses(prev =>
      prev.includes(nurseId)
        ? prev.filter(id => id !== nurseId)
        : [...prev, nurseId]
    );
  };

  // Select All / Deselect All helpers
  const selectAllDoctors = () => {
    setSelectedDoctors(filteredDoctors.map(d => d.id));
  };

  const deselectAllDoctors = () => {
    // Only deselect filtered doctors (so search + deselect works intuitively)
    const filteredIds = filteredDoctors.map(d => d.id);
    setSelectedDoctors(prev => prev.filter(id => !filteredIds.includes(id)));
  };

  const selectAllHospitals = () => {
    setSelectedHospitals(hospitals.map(h => h.id));
  };

  const deselectAllHospitals = () => {
    setSelectedHospitals([]);
  };

  const selectAllSpecializations = () => {
    setSelectedSpecializations([...specializations]);
  };

  const deselectAllSpecializations = () => {
    setSelectedSpecializations([]);
  };

  const selectAllNurses = () => {
    setSelectedNurses(filteredNurses.map(n => n.id));
  };

  const deselectAllNurses = () => {
    // Only deselect filtered nurses (so search + deselect works intuitively)
    const filteredIds = filteredNurses.map(n => n.id);
    setSelectedNurses(prev => prev.filter(id => !filteredIds.includes(id)));
  };

  // Filter doctors based on search query
  const filteredDoctors = doctors.filter(doc =>
    doc.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    doc.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (doc.specialization && doc.specialization.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  // Filter nurses based on search query
  const filteredNurses = nurses.filter(nurse =>
    nurse.full_name.toLowerCase().includes(nurseSearchQuery.toLowerCase()) ||
    nurse.email.toLowerCase().includes(nurseSearchQuery.toLowerCase()) ||
    (nurse.qualification && nurse.qualification.toLowerCase().includes(nurseSearchQuery.toLowerCase()))
  );

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 p-4 pt-8">
      <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="border-b border-gray-200 px-6 py-4 flex items-center justify-between sticky top-0 bg-white">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Share Template</h2>
            <p className="text-sm text-gray-600 mt-1">{template?.template_name}</p>
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

          {/* Loading State */}
          {loading && (
            <div className="flex items-center justify-center py-8">
              <svg className="animate-spin h-8 w-8 text-blue-600" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            </div>
          )}

          {!loading && (
            <>
              {/* Tabs */}
              <div className="border-b border-gray-200">
                <nav className="flex space-x-8">
                  <button
                    onClick={() => setActiveTab('individual')}
                    className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                      activeTab === 'individual'
                        ? 'border-blue-500 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }`}
                  >
                    Individual Doctors ({selectedDoctors.length})
                  </button>
                  <button
                    onClick={() => setActiveTab('hospital')}
                    className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                      activeTab === 'hospital'
                        ? 'border-blue-500 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }`}
                  >
                    By Hospital ({selectedHospitals.length})
                  </button>
                  <button
                    onClick={() => setActiveTab('specialization')}
                    className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                      activeTab === 'specialization'
                        ? 'border-blue-500 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }`}
                  >
                    By Specialization ({selectedSpecializations.length})
                  </button>
                  <button
                    onClick={() => setActiveTab('nurses')}
                    className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                      activeTab === 'nurses'
                        ? 'border-teal-500 text-teal-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }`}
                  >
                    Nurses ({selectedNurses.length})
                  </button>
                </nav>
              </div>

              {/* Owner Selection for Global Templates (not needed for Nurses tab) */}
              {isGlobalTemplate && activeTab !== 'nurses' && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <svg className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                    <div className="flex-1">
                      <h4 className="text-sm font-medium text-amber-800">
                        Global Template - Owner Required
                      </h4>
                      <p className="text-xs text-amber-700 mt-1">
                        This is a global template visible to all doctors. To restrict access, you must first assign an owner.
                        The template will no longer be globally visible after sharing.
                      </p>
                      <div className="mt-3">
                        <label className="block text-sm font-medium text-amber-800 mb-1">
                          Select Template Owner <span className="text-red-500">*</span>
                        </label>
                        <select
                          value={selectedOwner}
                          onChange={(e) => setSelectedOwner(e.target.value)}
                          className="w-full px-3 py-2 border border-amber-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 text-gray-900 bg-white"
                        >
                          <option value="">-- Select owner --</option>
                          {doctors.map((doctor) => (
                            <option key={doctor.id} value={doctor.id}>
                              {doctor.full_name} {doctor.specialization ? `(${doctor.specialization})` : ''}
                            </option>
                          ))}
                        </select>
                        <p className="text-xs text-amber-600 mt-1">
                          The owner will automatically receive access to this template.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Tab Content */}
              <div className="space-y-4">
                {activeTab === 'individual' && (
                  <div className="space-y-4">
                    {/* Search Bar */}
                    <div>
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search doctors by name, email, or specialization..."
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                      />
                    </div>

                    {/* Select All / Deselect All */}
                    {filteredDoctors.length > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">
                          {selectedDoctors.length} of {doctors.length} selected
                          {searchQuery && ` (showing ${filteredDoctors.length})`}
                        </span>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={selectAllDoctors}
                            className="px-3 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50 rounded transition-colors"
                          >
                            Select All{searchQuery ? ' Visible' : ''}
                          </button>
                          <button
                            type="button"
                            onClick={deselectAllDoctors}
                            className="px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 rounded transition-colors"
                          >
                            Deselect All{searchQuery ? ' Visible' : ''}
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Doctors List */}
                    <div className="max-h-96 overflow-y-auto border border-gray-200 rounded-lg">
                      {filteredDoctors.length === 0 ? (
                        <div className="text-center py-8 text-gray-500">
                          {searchQuery ? 'No doctors found matching your search.' : 'No doctors available.'}
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

                {activeTab === 'hospital' && (
                  <div className="space-y-4">
                    {/* Select All / Deselect All */}
                    {hospitals.length > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">
                          {selectedHospitals.length} of {hospitals.length} selected
                        </span>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={selectAllHospitals}
                            className="px-3 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50 rounded transition-colors"
                          >
                            Select All
                          </button>
                          <button
                            type="button"
                            onClick={deselectAllHospitals}
                            className="px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 rounded transition-colors"
                          >
                            Deselect All
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Hospitals List */}
                    <div className="max-h-96 overflow-y-auto border border-gray-200 rounded-lg">
                      {hospitals.length === 0 ? (
                        <div className="text-center py-8 text-gray-500">No hospitals available.</div>
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
                    <p className="text-xs text-gray-500">
                      All active doctors in the selected hospitals will receive access
                    </p>
                  </div>
                )}

                {activeTab === 'specialization' && (
                  <div className="space-y-4">
                    {/* Select All / Deselect All */}
                    {specializations.length > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">
                          {selectedSpecializations.length} of {specializations.length} selected
                        </span>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={selectAllSpecializations}
                            className="px-3 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50 rounded transition-colors"
                          >
                            Select All
                          </button>
                          <button
                            type="button"
                            onClick={deselectAllSpecializations}
                            className="px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 rounded transition-colors"
                          >
                            Deselect All
                          </button>
                        </div>
                      </div>
                    )}

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
                    <p className="text-xs text-gray-500">
                      All doctors with the selected specializations will receive access
                    </p>
                  </div>
                )}

                {activeTab === 'nurses' && (
                  <div className="space-y-4">
                    {/* Search Bar */}
                    <div>
                      <input
                        type="text"
                        value={nurseSearchQuery}
                        onChange={(e) => setNurseSearchQuery(e.target.value)}
                        placeholder="Search nurses by name, email, or qualification..."
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 focus:border-teal-500 text-gray-900 bg-white"
                      />
                    </div>

                    {/* Select All / Deselect All */}
                    {filteredNurses.length > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">
                          {selectedNurses.length} of {nurses.length} selected
                          {nurseSearchQuery && ` (showing ${filteredNurses.length})`}
                        </span>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={selectAllNurses}
                            className="px-3 py-1 text-xs font-medium text-teal-600 hover:bg-teal-50 rounded transition-colors"
                          >
                            Select All{nurseSearchQuery ? ' Visible' : ''}
                          </button>
                          <button
                            type="button"
                            onClick={deselectAllNurses}
                            className="px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 rounded transition-colors"
                          >
                            Deselect All{nurseSearchQuery ? ' Visible' : ''}
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Nurses List */}
                    <div className="max-h-96 overflow-y-auto border border-gray-200 rounded-lg">
                      {filteredNurses.length === 0 ? (
                        <div className="text-center py-8 text-gray-500">
                          {nurseSearchQuery ? 'No nurses found matching your search.' : 'No nurses available.'}
                        </div>
                      ) : (
                        <div className="divide-y divide-gray-200">
                          {filteredNurses.map((nurse) => (
                            <label
                              key={nurse.id}
                              className="flex items-center p-3 hover:bg-gray-50 cursor-pointer"
                            >
                              <input
                                type="checkbox"
                                checked={selectedNurses.includes(nurse.id)}
                                onChange={() => toggleNurse(nurse.id)}
                                className="w-4 h-4 text-teal-600 focus:ring-teal-500 rounded"
                              />
                              <div className="ml-3 flex-1">
                                <div className="font-medium text-sm text-gray-900">{nurse.full_name}</div>
                                <div className="text-xs text-gray-500">
                                  {nurse.email}
                                  {nurse.qualification && ` • ${nurse.qualification}`}
                                </div>
                              </div>
                              {/* Show if already shared */}
                              {sharedNurses.some(s => s.nurse_id === nurse.id) && (
                                <span className="text-xs text-teal-600 bg-teal-50 px-2 py-0.5 rounded">
                                  Shared
                                </span>
                              )}
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                    <p className="text-xs text-gray-500">
                      Nurses will be able to use this template when recording on behalf of doctors
                    </p>
                  </div>
                )}

                {/* All shared templates have full use access */}
              </div>
            </>
          )}

          {/* Currently Shared With */}
          {sharedDoctors.length > 0 && (
            <div className="border-t border-gray-200 pt-6">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">
                Currently Shared With ({sharedDoctors.length})
              </h3>
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {sharedDoctors.map((sharing) => (
                  <div
                    key={sharing.id}
                    className="flex items-center justify-between bg-gray-50 rounded-lg p-3"
                  >
                    <div className="flex-1">
                      <p className="text-sm font-medium text-gray-900">
                        {sharing.doctor_name || 'Doctor'}
                      </p>
                      <p className="text-xs text-gray-500">
                        {sharing.is_active ? 'Shared' : 'Removed'}
                      </p>
                    </div>
                    <button
                      onClick={() => handleRevoke(sharing.doctor_id)}
                      className="text-red-600 hover:text-red-700 text-sm font-medium"
                    >
                      Revoke
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 px-6 py-4 flex items-center justify-end space-x-3 bg-gray-50">
          <button
            onClick={handleClose}
            className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 font-medium transition-colors"
          >
            Close
          </button>
          <button
            onClick={handleShare}
            disabled={sharing || loading}
            className={`px-4 py-2 rounded-lg font-medium transition-all ${
              sharing || loading
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm hover:shadow'
            }`}
          >
            {sharing ? (
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
                Sharing...
              </span>
            ) : (
              'Share Template'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
