'use client';

/**
 * Hard Delete Tab (Admin Only)
 *
 * PURPOSE:
 * Permanently delete soft-deleted entities from the database.
 * - Lists all is_active=false entities (segments, templates, consultation types)
 * - Shows relationships/dependencies inline
 * - Supports multi-select for batch deletion
 * - Performs hard DELETE from database with CASCADE
 *
 * DANGER: This is a PERMANENT operation that cannot be undone.
 */

import React, { useState, useEffect } from 'react';
import { handleApiError } from '@lib/summaryApi';
import { useAuth } from '@lib/auth';
import { authGet, authDelete, authPost } from '@lib/apiClient';

interface SoftDeletedEntity {
  id: string;
  segment_code?: string;
  segment_name?: string;
  template_code?: string;
  template_name?: string;
  type_code?: string;
  type_name?: string;
  default_category?: string;
  consultation_type_id?: string;
  counsellor_id?: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

interface EntityRelationships {
  entity_type: string;
  entity_id: string;
  relationships: {
    consultation_types?: Array<{ id: string; type_code: string; type_name: string }>;
    templates?: Array<{ id: string; template_code: string; template_name: string; counsellor_id?: string }>;
    segments?: Array<{ segment_id?: string; segment_code: string; category?: string; default_category?: string }>;
    counsellors?: Array<{ id: string; name: string; email: string; specialty?: string }>;
  };
}

type EntityType = 'segment' | 'template' | 'consultation_type';

// Modal component to show detailed relationships
function RelationshipDetails({
  relationships,
  children
}: {
  relationships: EntityRelationships;
  children: React.ReactNode;
}) {
  const [showModal, setShowModal] = useState(false);

  const hasRelationships =
    (relationships.relationships.consultation_types?.length || 0) > 0 ||
    (relationships.relationships.templates?.length || 0) > 0 ||
    (relationships.relationships.segments?.length || 0) > 0 ||
    (relationships.relationships.counsellors?.length || 0) > 0;

  if (!hasRelationships) {
    return <>{children}</>;
  }

  return (
    <>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation(); // Prevent row selection
          setShowModal(true);
        }}
        className="cursor-pointer underline decoration-dotted hover:text-yellow-800 text-left"
      >
        {children}
      </button>

      {showModal && (
        <div
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50"
          onClick={() => setShowModal(false)}
        >
          <div
            className="bg-white rounded-lg shadow-2xl w-full max-w-md mx-4 max-h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()} // Prevent closing when clicking inside
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <h5 className="font-semibold text-gray-900">
                Will be CASCADE deleted:
              </h5>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="text-gray-400 hover:text-gray-600 p-1 rounded hover:bg-gray-100"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Content */}
            <div className="p-4 space-y-4 overflow-y-auto flex-1">
              {relationships.relationships.consultation_types && relationships.relationships.consultation_types.length > 0 && (
                <div>
                  <h6 className="text-xs font-semibold text-yellow-700 uppercase tracking-wide mb-2">
                    Session Types ({relationships.relationships.consultation_types.length})
                  </h6>
                  <ul className="space-y-1.5">
                    {relationships.relationships.consultation_types.map((ct) => (
                      <li key={ct.id} className="text-sm text-gray-700 flex items-center gap-2">
                        <span className="font-mono bg-gray-100 px-2 py-0.5 rounded text-gray-600 text-xs">
                          {ct.type_code}
                        </span>
                        <span>{ct.type_name}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {relationships.relationships.templates && relationships.relationships.templates.length > 0 && (
                <div>
                  <h6 className="text-xs font-semibold text-yellow-700 uppercase tracking-wide mb-2">
                    Templates ({relationships.relationships.templates.length})
                  </h6>
                  <ul className="space-y-1.5">
                    {relationships.relationships.templates.map((tmpl) => (
                      <li key={tmpl.id} className="text-sm text-gray-700 flex items-center gap-2">
                        <span className="font-mono bg-gray-100 px-2 py-0.5 rounded text-gray-600 text-xs">
                          {tmpl.template_code}
                        </span>
                        <span>{tmpl.template_name}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {relationships.relationships.segments && relationships.relationships.segments.length > 0 && (
                <div>
                  <h6 className="text-xs font-semibold text-yellow-700 uppercase tracking-wide mb-2">
                    Segments ({relationships.relationships.segments.length})
                  </h6>
                  <ul className="space-y-1.5">
                    {relationships.relationships.segments.map((seg, idx) => (
                      <li key={seg.segment_id || idx} className="text-sm text-gray-700 flex items-center gap-2">
                        <span className="font-mono bg-gray-100 px-2 py-0.5 rounded text-gray-600 text-xs">
                          {seg.segment_code}
                        </span>
                        {seg.category && <span className="text-gray-500">({seg.category})</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {relationships.relationships.counsellors && relationships.relationships.counsellors.length > 0 && (
                <div>
                  <h6 className="text-xs font-semibold text-yellow-700 uppercase tracking-wide mb-2">
                    Counsellors ({relationships.relationships.counsellors.length})
                  </h6>
                  <ul className="space-y-1.5">
                    {relationships.relationships.counsellors.map((doc) => (
                      <li key={doc.id} className="text-sm text-gray-700">
                        <span className="font-medium">{doc.name}</span>
                        <span className="text-gray-500 ml-1">({doc.email})</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-4 py-3 border-t border-gray-200 bg-gray-50 rounded-b-lg">
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="w-full px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors font-medium"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function HardDeleteTab() {
  const { getAccessToken } = useAuth();
  const [entityType, setEntityType] = useState<EntityType>('segment');
  const [entities, setEntities] = useState<SoftDeletedEntity[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [relationshipsMap, setRelationshipsMap] = useState<Map<string, EntityRelationships>>(new Map());
  const [loading, setLoading] = useState(false);
  const [loadingRelationships, setLoadingRelationships] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Fetch soft-deleted entities when entity type changes
  useEffect(() => {
    fetchSoftDeletedEntities();
  }, [entityType]);

  // Clear selection when entity type changes
  useEffect(() => {
    setSelectedIds(new Set());
    setRelationshipsMap(new Map());
    setError(null);
    setSuccess(null);
  }, [entityType]);

  const fetchSoftDeletedEntities = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await authGet(
        `/api/v1/summary/admin/soft-deleted/${entityType}`,
        getAccessToken()
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch soft-deleted ${entityType}s`);
      }

      const data = await response.json();
      const items = data.items || [];
      setEntities(items);

      // Fetch relationships for all entities
      if (items.length > 0) {
        fetchAllRelationships(items);
      }
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const fetchAllRelationships = async (items: SoftDeletedEntity[]) => {
    setLoadingRelationships(true);
    const newMap = new Map<string, EntityRelationships>();

    // Fetch relationships in parallel (batch of 5 at a time)
    const batchSize = 5;
    for (let i = 0; i < items.length; i += batchSize) {
      const batch = items.slice(i, i + batchSize);
      const promises = batch.map(async (entity) => {
        try {
          const response = await authGet(
            `/api/v1/summary/admin/relationships/${entityType}/${entity.id}`,
            getAccessToken()
          );
          if (response.ok) {
            const data = await response.json();
            return { id: entity.id, data };
          }
        } catch {
          // Ignore errors for individual fetches
        }
        return null;
      });

      const results = await Promise.all(promises);
      results.forEach((result) => {
        if (result) {
          newMap.set(result.id, result.data);
        }
      });
    }

    setRelationshipsMap(newMap);
    setLoadingRelationships(false);
  };

  const toggleSelection = (entityId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(entityId)) {
        next.delete(entityId);
      } else {
        next.add(entityId);
      }
      return next;
    });
  };

  const selectAll = () => {
    if (selectedIds.size === entities.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(entities.map(e => e.id)));
    }
  };

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) {
      setError('Please select at least one entity to delete');
      return;
    }

    const confirmed = window.confirm(
      `⚠️ DANGER: This will PERMANENTLY delete ${selectedIds.size} ${entityType}(s) from the database.\n\n` +
      `This action:\n` +
      `- Cannot be undone\n` +
      `- Will cascade delete all junction table entries\n` +
      `- May affect other entities\n\n` +
      `Are you absolutely sure you want to proceed?`
    );

    if (!confirmed) return;

    setDeleting(true);
    setError(null);
    setSuccess(null);

    const results: { success: string[]; failed: string[] } = { success: [], failed: [] };

    for (const entityId of selectedIds) {
      try {
        const response = await authDelete(
          `/api/v1/summary/admin/hard-delete/${entityType}/${entityId}?admin_id=admin-user-1`,
          getAccessToken()
        );

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Failed to delete entity');
        }

        const result = await response.json();
        results.success.push(result.entity_name || entityId);
      } catch {
        const entity = entities.find(e => e.id === entityId);
        results.failed.push(entity ? getEntityDisplayName(entity) : entityId);
      }
    }

    setDeleting(false);

    if (results.success.length > 0) {
      setSuccess(`Successfully deleted ${results.success.length} ${entityType}(s)`);
    }
    if (results.failed.length > 0) {
      setError(`Failed to delete: ${results.failed.join(', ')}`);
    }

    // Refresh the list and clear selection
    setSelectedIds(new Set());
    setRelationshipsMap(new Map());
    await fetchSoftDeletedEntities();
  };

  const handleBatchActivate = async () => {
    if (selectedIds.size === 0) {
      setError('Please select at least one entity to reactivate');
      return;
    }

    const confirmed = window.confirm(
      `This will reactivate ${selectedIds.size} ${entityType}(s).\n\n` +
      `The selected entities will become active again and visible in the system.\n\n` +
      `Do you want to proceed?`
    );

    if (!confirmed) return;

    setActivating(true);
    setError(null);
    setSuccess(null);

    const results: { success: string[]; failed: string[] } = { success: [], failed: [] };

    for (const entityId of selectedIds) {
      const entity = entities.find(e => e.id === entityId);
      if (!entity) continue;

      try {
        // Build the correct endpoint based on entity type
        let endpoint: string;
        if (entityType === 'segment') {
          endpoint = `/api/v1/summary/admin/segments/${entityId}/reactivate`;
        } else if (entityType === 'template') {
          endpoint = `/api/v1/summary/admin/templates/${entity.template_code}/reactivate`;
        } else {
          endpoint = `/api/v1/summary/admin/consultation-types/${entity.type_code}/reactivate`;
        }

        const response = await authPost(endpoint, getAccessToken(), {});

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Failed to reactivate entity');
        }

        results.success.push(getEntityDisplayName(entity));
      } catch {
        results.failed.push(entity ? getEntityDisplayName(entity) : entityId);
      }
    }

    setActivating(false);

    if (results.success.length > 0) {
      setSuccess(`Successfully reactivated ${results.success.length} ${entityType}(s)`);
    }
    if (results.failed.length > 0) {
      setError(`Failed to reactivate: ${results.failed.join(', ')}`);
    }

    // Refresh the list and clear selection
    setSelectedIds(new Set());
    setRelationshipsMap(new Map());
    await fetchSoftDeletedEntities();
  };

  const getEntityDisplayName = (entity: SoftDeletedEntity): string => {
    if (entityType === 'segment') {
      return `${entity.segment_code} - ${entity.segment_name}`;
    } else if (entityType === 'template') {
      return `${entity.template_code} - ${entity.template_name}`;
    } else {
      return `${entity.type_code} - ${entity.type_name}`;
    }
  };

  const getEntityCode = (entity: SoftDeletedEntity): string => {
    if (entityType === 'segment') return entity.segment_code || '';
    if (entityType === 'template') return entity.template_code || '';
    return entity.type_code || '';
  };

  const getEntityName = (entity: SoftDeletedEntity): string => {
    if (entityType === 'segment') return entity.segment_name || '';
    if (entityType === 'template') return entity.template_name || '';
    return entity.type_name || '';
  };

  const getRelationshipSummary = (entityId: string): { count: number; details: string[] } => {
    const rel = relationshipsMap.get(entityId);
    if (!rel) return { count: 0, details: [] };

    const details: string[] = [];
    let count = 0;

    if (rel.relationships.consultation_types?.length) {
      const c = rel.relationships.consultation_types.length;
      count += c;
      details.push(`${c} session type${c > 1 ? 's' : ''}`);
    }
    if (rel.relationships.templates?.length) {
      const c = rel.relationships.templates.length;
      count += c;
      details.push(`${c} template${c > 1 ? 's' : ''}`);
    }
    if (rel.relationships.segments?.length) {
      const c = rel.relationships.segments.length;
      count += c;
      details.push(`${c} segment${c > 1 ? 's' : ''}`);
    }
    if (rel.relationships.counsellors?.length) {
      const c = rel.relationships.counsellors.length;
      count += c;
      details.push(`${c} counsellor${c > 1 ? 's' : ''}`);
    }

    return { count, details };
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="flex items-start space-x-3">
          <svg className="w-6 h-6 text-red-600 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-red-900">Hard Delete (Permanent)</h3>
            <p className="text-sm text-red-700 mt-1">
              Select entities to permanently remove from the database. Relationships shown will be CASCADE deleted.
            </p>
          </div>
        </div>
      </div>

      {/* Entity Type Selector */}
      <div className="space-y-2">
        <label className="block text-sm font-medium text-gray-700">Entity Type</label>
        <div className="flex space-x-2">
          {(['segment', 'template', 'consultation_type'] as EntityType[]).map((type) => (
            <button
              key={type}
              onClick={() => setEntityType(type)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                entityType === type
                  ? 'bg-red-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {type === 'consultation_type' ? 'Session Type' : type.charAt(0).toUpperCase() + type.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Error/Success Messages */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}
      {success && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <p className="text-sm text-green-700">{success}</p>
        </div>
      )}

      {/* Entity List with Multi-Select */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="block text-sm font-medium text-gray-700">
            Soft-Deleted {entityType === 'consultation_type' ? 'Session Types' : entityType.charAt(0).toUpperCase() + entityType.slice(1) + 's'}
            {loading && ' (Loading...)'}
            {loadingRelationships && ' (Loading relationships...)'}
          </label>
          {entities.length > 0 && (
            <button
              onClick={selectAll}
              className="text-sm text-blue-600 hover:text-blue-700 font-medium"
            >
              {selectedIds.size === entities.length ? 'Deselect All' : 'Select All'}
            </button>
          )}
        </div>

        {loading ? (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-600 mx-auto mb-2"></div>
            <p className="text-sm text-gray-500">Loading soft-deleted entities...</p>
          </div>
        ) : entities.length === 0 ? (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
            <svg className="w-12 h-12 text-gray-400 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-sm text-gray-500">No soft-deleted {entityType}s found</p>
          </div>
        ) : (
          <div className="bg-white border border-gray-200 rounded-lg divide-y divide-gray-100 max-h-[500px] overflow-y-auto">
            {entities.map((entity) => {
              const { count: relCount, details: relDetails } = getRelationshipSummary(entity.id);
              const isSelected = selectedIds.has(entity.id);

              return (
                <div
                  key={entity.id}
                  onClick={() => toggleSelection(entity.id)}
                  className={`flex items-start px-4 py-3 cursor-pointer transition-colors ${
                    isSelected ? 'bg-red-50 hover:bg-red-100' : 'hover:bg-gray-50'
                  }`}
                >
                  {/* Checkbox */}
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => {}}
                    className="w-4 h-4 mt-1 text-red-600 border-gray-300 rounded focus:ring-red-500 cursor-pointer"
                  />

                  {/* Entity Info */}
                  <div className="ml-3 flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-mono bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                        {getEntityCode(entity)}
                      </span>
                      <span className="text-sm font-medium text-gray-900">
                        {getEntityName(entity)}
                      </span>
                      {entity.default_category && (
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          entity.default_category === 'core'
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}>
                          {entity.default_category}
                        </span>
                      )}
                    </div>

                    {/* Relationships inline */}
                    <div className="mt-1 flex items-center gap-2 text-xs">
                      {loadingRelationships ? (
                        <span className="text-gray-400">Loading relationships...</span>
                      ) : relCount === 0 ? (
                        <span className="text-green-600 flex items-center gap-1">
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                          </svg>
                          No relationships - safe to delete
                        </span>
                      ) : relationshipsMap.get(entity.id) ? (
                        <span className="text-yellow-700 flex items-center gap-1">
                          <svg className="w-3 h-3 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                          </svg>
                          <RelationshipDetails relationships={relationshipsMap.get(entity.id)!}>
                            CASCADE: {relDetails.join(', ')} (click for details)
                          </RelationshipDetails>
                        </span>
                      ) : (
                        <span className="text-yellow-700 flex items-center gap-1">
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                          </svg>
                          CASCADE: {relDetails.join(', ')}
                        </span>
                      )}
                    </div>

                    {/* Created date */}
                    {entity.created_at && (
                      <div className="mt-1 text-xs text-gray-400">
                        Created: {new Date(entity.created_at).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Selection Summary & Action Buttons */}
      {entities.length > 0 && (
        <div className="flex items-center justify-between bg-gray-50 border border-gray-200 rounded-lg px-4 py-3">
          <div className="text-sm text-gray-600">
            {selectedIds.size === 0 ? (
              'Click on rows to select entities'
            ) : (
              <span className="font-medium text-gray-700">
                {selectedIds.size} {entityType}(s) selected
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {/* Activate Again Button */}
            <button
              onClick={handleBatchActivate}
              disabled={activating || deleting || selectedIds.size === 0}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {activating ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                  Activating...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Activate Again ({selectedIds.size})
                </>
              )}
            </button>
            {/* Delete Button */}
            <button
              onClick={handleBatchDelete}
              disabled={deleting || activating || selectedIds.size === 0}
              className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {deleting ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                  Deleting...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  Delete Selected ({selectedIds.size})
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
