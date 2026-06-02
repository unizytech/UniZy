'use client';

import React, { useState, useEffect } from 'react';
import {
  shareTemplate,
  shareTemplateWithSchool,
  shareTemplateWithSpecialization,
  revokeTemplateAccess,
  getTemplateShares,
  handleApiError
} from "@lib/summaryApi";
import {
  getAllCounsellorsForSharing,
  getSchools,
  getSpecializations,
  CounsellorListItem,
  School
} from "@/services/counsellorApi";
import {
  getAllAssistantsForSharing,
  shareTemplateWithAssistants,
  getTemplateAssistantShares,
  revokeAssistantTemplateAccess,
  type AssistantListItem
} from "@/services/assistantApi";
import { useAuth } from '@lib/auth';

interface ShareTemplateModalProps {
  template: any;
  isOpen: boolean;
  onClose: () => void;
  onShareComplete?: () => void;
}

type ShareTab = 'individual' | 'school' | 'specialization' | 'assistants';

export function ShareTemplateModal({
  template,
  isOpen,
  onClose,
  onShareComplete
}: ShareTemplateModalProps) {
  const { getAccessToken } = useAuth();
  const [activeTab, setActiveTab] = useState<ShareTab>('individual');
  const [selectedCounsellors, setSelectedCounsellors] = useState<string[]>([]);
  const [selectedSchools, setSelectedSchools] = useState<string[]>([]);
  const [selectedSpecializations, setSelectedSpecializations] = useState<string[]>([]);
  // accessLevel removed — all shares are now 'use'
  const [sharing, setSharing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [sharedCounsellors, setSharedCounsellors] = useState<any[]>([]);

  // Owner selection for global templates
  const [selectedOwner, setSelectedOwner] = useState<string>('');
  const isGlobalTemplate = !template?.counsellor_id;

  // Track initial state for comparison (to detect adds/removes)
  const [initialSchoolIds, setInitialSchoolIds] = useState<string[]>([]);
  const [initialSpecializations, setInitialSpecializations] = useState<string[]>([]);

  // Data fetching states
  const [counsellors, setCounsellors] = useState<CounsellorListItem[]>([]);
  const [schools, setSchools] = useState<School[]>([]);
  const [specializations, setSpecializations] = useState<string[]>([]);
  const [assistants, setAssistants] = useState<AssistantListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [assistantSearchQuery, setAssistantSearchQuery] = useState('');

  // Assistant selection state
  const [selectedAssistants, setSelectedAssistants] = useState<string[]>([]);
  const [sharedAssistants, setSharedAssistants] = useState<Array<{ assistant_id: string; is_active: boolean }>>([]);
  const [initialAssistantIds, setInitialAssistantIds] = useState<string[]>([]);

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
      const [counsellorsData, schoolsData, specializationsData, sharesData, assistantsData, assistantSharesData] = await Promise.all([
        getAllCounsellorsForSharing(token),
        getSchools(token),
        getSpecializations(token),
        getTemplateShares(template.id, token),
        getAllAssistantsForSharing(token),
        getTemplateAssistantShares(template.id, token)
      ]);

      setCounsellors(counsellorsData);
      setSchools(schoolsData);
      setSpecializations(specializationsData);
      setAssistants(assistantsData);

      // Set existing counsellor shares
      if (sharesData.success) {
        setSharedCounsellors(sharesData.shares.counsellors);

        // Pre-select existing shares
        setSelectedCounsellors(sharesData.shares.counsellors.map(d => d.counsellor_id));
        setSelectedSchools(sharesData.shares.school_ids);
        setSelectedSpecializations(sharesData.shares.specializations);

        // Store initial state for comparison when saving
        setInitialSchoolIds(sharesData.shares.school_ids);
        setInitialSpecializations(sharesData.shares.specializations);
      }

      // Set existing assistant shares
      if (assistantSharesData && assistantSharesData.length > 0) {
        setSharedAssistants(assistantSharesData);
        setSelectedAssistants(assistantSharesData.map(s => s.assistant_id));
        setInitialAssistantIds(assistantSharesData.map(s => s.assistant_id));
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

      // Validate owner selection for global templates (only for counsellor tabs, not assistants)
      if (isGlobalTemplate && !selectedOwner && activeTab !== 'assistants') {
        setError('Please select a template owner before sharing. This will convert the global template to a counsellor-owned template.');
        setSharing(false);
        return;
      }

      let totalShared = 0;
      let totalRemoved = 0;
      let ownershipAssigned = false;

      // For global templates, pass the selectedOwner to assign ownership
      const newOwnerId = isGlobalTemplate ? selectedOwner : undefined;

      // Determine who is sharing: existing owner for counsellor templates, or selected owner for global templates
      const sharingCounsellorId = template.counsellor_id || selectedOwner;

      // Each tab operates independently - only process the active tab's selections
      if (activeTab === 'individual') {
        // COUNSELLORS TAB: Add/remove individual counsellor shares
        // Ignore schools and specializations state completely
        const existingCounsellorIds = sharedCounsellors.map(d => d.counsellor_id);
        const counsellorsToAdd = selectedCounsellors.filter(id => !existingCounsellorIds.includes(id));
        const counsellorsToRemove = existingCounsellorIds.filter(id => !selectedCounsellors.includes(id));

        // Add new shares (with ownership assignment for global templates)
        const token = getAccessToken();
        if (counsellorsToAdd.length > 0) {
          const result = await shareTemplate(sharingCounsellorId, template.id, counsellorsToAdd, newOwnerId, token);
          totalShared = result.shared_count;
          if (result.ownership_assigned) {
            ownershipAssigned = true;
          }
        } else if (newOwnerId) {
          // Even if no counsellors to add, we need to assign ownership
          // Create a share for just the owner
          const result = await shareTemplate(sharingCounsellorId, template.id, [newOwnerId], newOwnerId, token);
          if (result.ownership_assigned) {
            ownershipAssigned = true;
          }
        }

        // Remove unchecked shares
        if (counsellorsToRemove.length > 0) {
          for (const counsellorId of counsellorsToRemove) {
            await revokeTemplateAccess(sharingCounsellorId, counsellorId, template.id, token);
            totalRemoved++;
          }
        }

        if (ownershipAssigned) {
          const ownerName = counsellors.find(d => d.id === selectedOwner)?.full_name || 'selected counsellor';
          setSuccess(`Template ownership assigned to ${ownerName}. Shared with ${totalShared} counsellor(s)${totalRemoved > 0 ? `, removed ${totalRemoved}` : ''}`);
        } else if (totalShared > 0 && totalRemoved > 0) {
          setSuccess(`Updated shares: Added ${totalShared}, removed ${totalRemoved}`);
        } else if (totalShared > 0) {
          setSuccess(`Template shared with ${totalShared} new counsellor(s)`);
        } else if (totalRemoved > 0) {
          setSuccess(`Removed ${totalRemoved} counsellor share(s)`);
        } else {
          setSuccess('No changes made');
        }

      } else if (activeTab === 'school') {
        // SCHOOL TAB: Add/remove school shares
        // Ignore counsellors and specializations state completely
        const token = getAccessToken();

        // Determine which schools to add and which to remove
        const schoolsToAdd = selectedSchools.filter(id => !initialSchoolIds.includes(id));
        const schoolsToRemove = initialSchoolIds.filter(id => !selectedSchools.includes(id));

        // Add new school shares (pass owner on first share for global templates)
        let ownerPassedOnce = false;
        for (const schoolId of schoolsToAdd) {
          const ownerForThisCall = (!ownerPassedOnce && newOwnerId) ? newOwnerId : undefined;
          const result = await shareTemplateWithSchool(sharingCounsellorId, template.id, schoolId, ownerForThisCall, token);
          totalShared += result.shared_count;
          if (result.ownership_assigned) {
            ownershipAssigned = true;
            ownerPassedOnce = true;
          }
        }

        // If no schools to add but we need to assign ownership, do it via individual share
        if (schoolsToAdd.length === 0 && newOwnerId) {
          const result = await shareTemplate(sharingCounsellorId, template.id, [newOwnerId], newOwnerId, token);
          if (result.ownership_assigned) {
            ownershipAssigned = true;
          }
        }

        // Remove unchecked school shares (revoke from ALL counsellors in those schools)
        for (const schoolId of schoolsToRemove) {
          // Get all counsellors in this school from the sharedCounsellors list
          const counsellorsInSchool = sharedCounsellors
            .filter(d => d.school_id === schoolId)
            .map(d => d.counsellor_id);

          // Revoke access from each counsellor
          for (const counsellorId of counsellorsInSchool) {
            await revokeTemplateAccess(sharingCounsellorId, counsellorId, template.id, token);
            totalRemoved++;
          }
        }

        if (ownershipAssigned) {
          const ownerName = counsellors.find(d => d.id === selectedOwner)?.full_name || 'selected counsellor';
          setSuccess(`Template ownership assigned to ${ownerName}. Shared with ${totalShared} counsellor(s) across ${schoolsToAdd.length} school(s)`);
        } else if (totalShared > 0 && totalRemoved > 0) {
          setSuccess(`Updated shares: Added ${totalShared}, removed ${totalRemoved}`);
        } else if (totalShared > 0) {
          setSuccess(`Template shared with ${totalShared} counsellor(s) across ${schoolsToAdd.length} school(s)`);
        } else if (totalRemoved > 0) {
          setSuccess(`Removed template from ${totalRemoved} counsellor(s) in ${schoolsToRemove.length} school(s)`);
        } else {
          setSuccess('No changes made');
        }

      } else if (activeTab === 'specialization') {
        // SPECIALIZATION TAB: Add/remove specialization shares
        // Ignore counsellors and schools state completely
        const token = getAccessToken();

        // Determine which specializations to add and which to remove
        const specsToAdd = selectedSpecializations.filter(spec => !initialSpecializations.includes(spec));
        const specsToRemove = initialSpecializations.filter(spec => !selectedSpecializations.includes(spec));

        // Add new specialization shares (pass owner on first share for global templates)
        let ownerPassedOnce = false;
        for (const spec of specsToAdd) {
          const ownerForThisCall = (!ownerPassedOnce && newOwnerId) ? newOwnerId : undefined;
          const result = await shareTemplateWithSpecialization(sharingCounsellorId, template.id, spec, ownerForThisCall, token);
          totalShared += result.shared_count;
          if (result.ownership_assigned) {
            ownershipAssigned = true;
            ownerPassedOnce = true;
          }
        }

        // If no specializations to add but we need to assign ownership, do it via individual share
        if (specsToAdd.length === 0 && newOwnerId) {
          const result = await shareTemplate(sharingCounsellorId, template.id, [newOwnerId], newOwnerId, token);
          if (result.ownership_assigned) {
            ownershipAssigned = true;
          }
        }

        // Remove unchecked specialization shares (revoke from ALL counsellors with those specializations)
        for (const spec of specsToRemove) {
          // Get all counsellors with this specialization from the sharedCounsellors list
          const counsellorsWithSpec = sharedCounsellors
            .filter(d => d.specialization === spec)
            .map(d => d.counsellor_id);

          // Revoke access from each counsellor
          for (const counsellorId of counsellorsWithSpec) {
            await revokeTemplateAccess(sharingCounsellorId, counsellorId, template.id, token);
            totalRemoved++;
          }
        }

        if (ownershipAssigned) {
          const ownerName = counsellors.find(d => d.id === selectedOwner)?.full_name || 'selected counsellor';
          setSuccess(`Template ownership assigned to ${ownerName}. Shared with ${totalShared} counsellor(s) across ${specsToAdd.length} specialization(s)`);
        } else if (totalShared > 0 && totalRemoved > 0) {
          setSuccess(`Updated shares: Added ${totalShared}, removed ${totalRemoved}`);
        } else if (totalShared > 0) {
          setSuccess(`Template shared with ${totalShared} counsellor(s) across ${specsToAdd.length} specialization(s)`);
        } else if (totalRemoved > 0) {
          setSuccess(`Removed template from ${totalRemoved} counsellor(s) with ${specsToRemove.length} specialization(s)`);
        } else {
          setSuccess('No changes made');
        }
      } else if (activeTab === 'assistants') {
        // ASSISTANTS TAB: Add/remove assistant shares
        // Ignore counsellors, schools, and specializations state completely

        // Determine which assistants to add and which to remove
        const assistantsToAdd = selectedAssistants.filter(id => !initialAssistantIds.includes(id));
        const assistantsToRemove = initialAssistantIds.filter(id => !selectedAssistants.includes(id));

        // Add new assistant shares
        if (assistantsToAdd.length > 0) {
          const result = await shareTemplateWithAssistants(
            template.id,
            template.template_code,
            assistantsToAdd,
            getAccessToken()
          );
          totalShared = result.shared_count;
        }

        // Remove unchecked assistant shares
        for (const assistantId of assistantsToRemove) {
          await revokeAssistantTemplateAccess(assistantId, template.id, getAccessToken());
          totalRemoved++;
        }

        if (totalShared > 0 && totalRemoved > 0) {
          setSuccess(`Updated assistant shares: Added ${totalShared}, removed ${totalRemoved}`);
        } else if (totalShared > 0) {
          setSuccess(`Template shared with ${totalShared} assistant(s)`);
        } else if (totalRemoved > 0) {
          setSuccess(`Removed ${totalRemoved} assistant share(s)`);
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

  const handleRevoke = async (counsellorId: string) => {
    try {
      // The sharing counsellor is the template owner
      const sharingCounsellorId = template.counsellor_id;
      if (!sharingCounsellorId) {
        setError('Cannot revoke access from a global template. Please assign an owner first.');
        return;
      }
      const token = getAccessToken();
      await revokeTemplateAccess(sharingCounsellorId, counsellorId, template.id, token);
      setSuccess('Access revoked successfully');
      // Remove from both sharedCounsellors AND selectedCounsellors to prevent re-adding on share
      setSharedCounsellors(sharedCounsellors.filter(d => d.counsellor_id !== counsellorId));
      setSelectedCounsellors(prev => prev.filter(id => id !== counsellorId));
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handleClose = () => {
    setError(null);
    setSuccess(null);
    setSelectedCounsellors([]);
    setSelectedSchools([]);
    setSelectedSpecializations([]);
    setSelectedAssistants([]);
    setInitialSchoolIds([]);
    setInitialSpecializations([]);
    setInitialAssistantIds([]);
    setSearchQuery('');
    setAssistantSearchQuery('');
    setSelectedOwner('');
    onClose();
  };

  const toggleCounsellor = (counsellorId: string) => {
    setSelectedCounsellors(prev =>
      prev.includes(counsellorId)
        ? prev.filter(id => id !== counsellorId)
        : [...prev, counsellorId]
    );
  };

  const toggleSchool = (schoolId: string) => {
    setSelectedSchools(prev =>
      prev.includes(schoolId)
        ? prev.filter(id => id !== schoolId)
        : [...prev, schoolId]
    );
  };

  const toggleSpecialization = (spec: string) => {
    setSelectedSpecializations(prev =>
      prev.includes(spec)
        ? prev.filter(s => s !== spec)
        : [...prev, spec]
    );
  };

  const toggleAssistant = (assistantId: string) => {
    setSelectedAssistants(prev =>
      prev.includes(assistantId)
        ? prev.filter(id => id !== assistantId)
        : [...prev, assistantId]
    );
  };

  // Select All / Deselect All helpers
  const selectAllCounsellors = () => {
    setSelectedCounsellors(filteredCounsellors.map(d => d.id));
  };

  const deselectAllCounsellors = () => {
    // Only deselect filtered counsellors (so search + deselect works intuitively)
    const filteredIds = filteredCounsellors.map(d => d.id);
    setSelectedCounsellors(prev => prev.filter(id => !filteredIds.includes(id)));
  };

  const selectAllSchools = () => {
    setSelectedSchools(schools.map(h => h.id));
  };

  const deselectAllSchools = () => {
    setSelectedSchools([]);
  };

  const selectAllSpecializations = () => {
    setSelectedSpecializations([...specializations]);
  };

  const deselectAllSpecializations = () => {
    setSelectedSpecializations([]);
  };

  const selectAllAssistants = () => {
    setSelectedAssistants(filteredAssistants.map(n => n.id));
  };

  const deselectAllAssistants = () => {
    // Only deselect filtered assistants (so search + deselect works intuitively)
    const filteredIds = filteredAssistants.map(n => n.id);
    setSelectedAssistants(prev => prev.filter(id => !filteredIds.includes(id)));
  };

  // Filter counsellors based on search query
  const filteredCounsellors = counsellors.filter(doc =>
    doc.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    doc.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (doc.specialization && doc.specialization.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  // Filter assistants based on search query
  const filteredAssistants = assistants.filter(assistant =>
    assistant.full_name.toLowerCase().includes(assistantSearchQuery.toLowerCase()) ||
    assistant.email.toLowerCase().includes(assistantSearchQuery.toLowerCase()) ||
    (assistant.qualification && assistant.qualification.toLowerCase().includes(assistantSearchQuery.toLowerCase()))
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
                    Individual Counsellors ({selectedCounsellors.length})
                  </button>
                  <button
                    onClick={() => setActiveTab('school')}
                    className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                      activeTab === 'school'
                        ? 'border-blue-500 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }`}
                  >
                    By School ({selectedSchools.length})
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
                    onClick={() => setActiveTab('assistants')}
                    className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                      activeTab === 'assistants'
                        ? 'border-teal-500 text-teal-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }`}
                  >
                    Assistants ({selectedAssistants.length})
                  </button>
                </nav>
              </div>

              {/* Owner Selection for Global Templates (not needed for Assistants tab) */}
              {isGlobalTemplate && activeTab !== 'assistants' && (
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
                        This is a global template visible to all counsellors. To restrict access, you must first assign an owner.
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
                          {counsellors.map((counsellor) => (
                            <option key={counsellor.id} value={counsellor.id}>
                              {counsellor.full_name} {counsellor.specialization ? `(${counsellor.specialization})` : ''}
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
                        placeholder="Search counsellors by name, email, or specialization..."
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                      />
                    </div>

                    {/* Select All / Deselect All */}
                    {filteredCounsellors.length > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">
                          {selectedCounsellors.length} of {counsellors.length} selected
                          {searchQuery && ` (showing ${filteredCounsellors.length})`}
                        </span>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={selectAllCounsellors}
                            className="px-3 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50 rounded transition-colors"
                          >
                            Select All{searchQuery ? ' Visible' : ''}
                          </button>
                          <button
                            type="button"
                            onClick={deselectAllCounsellors}
                            className="px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 rounded transition-colors"
                          >
                            Deselect All{searchQuery ? ' Visible' : ''}
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Counsellors List */}
                    <div className="max-h-96 overflow-y-auto border border-gray-200 rounded-lg">
                      {filteredCounsellors.length === 0 ? (
                        <div className="text-center py-8 text-gray-500">
                          {searchQuery ? 'No counsellors found matching your search.' : 'No counsellors available.'}
                        </div>
                      ) : (
                        <div className="divide-y divide-gray-200">
                          {filteredCounsellors.map((counsellor) => (
                            <label
                              key={counsellor.id}
                              className="flex items-center p-3 hover:bg-gray-50 cursor-pointer"
                            >
                              <input
                                type="checkbox"
                                checked={selectedCounsellors.includes(counsellor.id)}
                                onChange={() => toggleCounsellor(counsellor.id)}
                                className="w-4 h-4 text-blue-600 focus:ring-blue-500 rounded"
                              />
                              <div className="ml-3 flex-1">
                                <div className="font-medium text-sm text-gray-900">{counsellor.full_name}</div>
                                <div className="text-xs text-gray-500">
                                  {counsellor.email}
                                  {counsellor.specialization && ` • ${counsellor.specialization}`}
                                </div>
                              </div>
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {activeTab === 'school' && (
                  <div className="space-y-4">
                    {/* Select All / Deselect All */}
                    {schools.length > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">
                          {selectedSchools.length} of {schools.length} selected
                        </span>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={selectAllSchools}
                            className="px-3 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50 rounded transition-colors"
                          >
                            Select All
                          </button>
                          <button
                            type="button"
                            onClick={deselectAllSchools}
                            className="px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 rounded transition-colors"
                          >
                            Deselect All
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Schools List */}
                    <div className="max-h-96 overflow-y-auto border border-gray-200 rounded-lg">
                      {schools.length === 0 ? (
                        <div className="text-center py-8 text-gray-500">No schools available.</div>
                      ) : (
                        <div className="divide-y divide-gray-200">
                          {schools.map((school) => (
                            <label
                              key={school.id}
                              className="flex items-center p-3 hover:bg-gray-50 cursor-pointer"
                            >
                              <input
                                type="checkbox"
                                checked={selectedSchools.includes(school.id)}
                                onChange={() => toggleSchool(school.id)}
                                className="w-4 h-4 text-blue-600 focus:ring-blue-500 rounded"
                              />
                              <div className="ml-3 flex-1">
                                <div className="font-medium text-sm text-gray-900">{school.school_name}</div>
                                <div className="text-xs text-gray-500">
                                  {school.city && school.state
                                    ? `${school.city}, ${school.state}`
                                    : school.city || school.state || 'Location not specified'}
                                </div>
                              </div>
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                    <p className="text-xs text-gray-500">
                      All active counsellors in the selected schools will receive access
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
                      All counsellors with the selected specializations will receive access
                    </p>
                  </div>
                )}

                {activeTab === 'assistants' && (
                  <div className="space-y-4">
                    {/* Search Bar */}
                    <div>
                      <input
                        type="text"
                        value={assistantSearchQuery}
                        onChange={(e) => setAssistantSearchQuery(e.target.value)}
                        placeholder="Search assistants by name, email, or qualification..."
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 focus:border-teal-500 text-gray-900 bg-white"
                      />
                    </div>

                    {/* Select All / Deselect All */}
                    {filteredAssistants.length > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">
                          {selectedAssistants.length} of {assistants.length} selected
                          {assistantSearchQuery && ` (showing ${filteredAssistants.length})`}
                        </span>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={selectAllAssistants}
                            className="px-3 py-1 text-xs font-medium text-teal-600 hover:bg-teal-50 rounded transition-colors"
                          >
                            Select All{assistantSearchQuery ? ' Visible' : ''}
                          </button>
                          <button
                            type="button"
                            onClick={deselectAllAssistants}
                            className="px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 rounded transition-colors"
                          >
                            Deselect All{assistantSearchQuery ? ' Visible' : ''}
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Assistants List */}
                    <div className="max-h-96 overflow-y-auto border border-gray-200 rounded-lg">
                      {filteredAssistants.length === 0 ? (
                        <div className="text-center py-8 text-gray-500">
                          {assistantSearchQuery ? 'No assistants found matching your search.' : 'No assistants available.'}
                        </div>
                      ) : (
                        <div className="divide-y divide-gray-200">
                          {filteredAssistants.map((assistant) => (
                            <label
                              key={assistant.id}
                              className="flex items-center p-3 hover:bg-gray-50 cursor-pointer"
                            >
                              <input
                                type="checkbox"
                                checked={selectedAssistants.includes(assistant.id)}
                                onChange={() => toggleAssistant(assistant.id)}
                                className="w-4 h-4 text-teal-600 focus:ring-teal-500 rounded"
                              />
                              <div className="ml-3 flex-1">
                                <div className="font-medium text-sm text-gray-900">{assistant.full_name}</div>
                                <div className="text-xs text-gray-500">
                                  {assistant.email}
                                  {assistant.qualification && ` • ${assistant.qualification}`}
                                </div>
                              </div>
                              {/* Show if already shared */}
                              {sharedAssistants.some(s => s.assistant_id === assistant.id) && (
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
                      Assistants will be able to use this template when recording on behalf of counsellors
                    </p>
                  </div>
                )}

                {/* All shared templates have full use access */}
              </div>
            </>
          )}

          {/* Currently Shared With */}
          {sharedCounsellors.length > 0 && (
            <div className="border-t border-gray-200 pt-6">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">
                Currently Shared With ({sharedCounsellors.length})
              </h3>
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {sharedCounsellors.map((sharing) => (
                  <div
                    key={sharing.id}
                    className="flex items-center justify-between bg-gray-50 rounded-lg p-3"
                  >
                    <div className="flex-1">
                      <p className="text-sm font-medium text-gray-900">
                        {sharing.counsellor_name || 'Counsellor'}
                      </p>
                      <p className="text-xs text-gray-500">
                        {sharing.is_active ? 'Shared' : 'Removed'}
                      </p>
                    </div>
                    <button
                      onClick={() => handleRevoke(sharing.counsellor_id)}
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
