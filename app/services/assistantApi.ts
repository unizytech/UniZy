/**
 * Assistant API Service
 *
 * Provides API client functions for assistant management endpoints.
 */

import { authGet, authPost, authPut, authDelete } from '@lib/apiClient';

export interface Assistant {
  id: string;
  email: string;
  full_name: string;
  qualification: string | null;
  school_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateAssistantRequest {
  email: string;
  full_name: string;
  qualification?: string;
  school_id?: string;
}

export interface UpdateAssistantRequest {
  email?: string;
  full_name?: string;
  qualification?: string;
  school_id?: string;
  is_active?: boolean;
}

export interface AssistantTemplate {
  id: string;
  assistant_id: string;
  template_id: string;
  template_code: string;
  template_name?: string;
  consultation_type_code?: string;
  consultation_type_name?: string;
  description?: string;
  is_active: boolean;
  activated_at: string | null;
  created_at: string;
}

export interface AssistantListItem {
  id: string;
  full_name: string;
  email: string;
  qualification: string | null;
}

export interface AssistantCounsellor {
  id: string;
  counsellor_id: string;
  counsellor_name: string;
  counsellor_email: string;
  specialization: string | null;
  is_active: boolean;
}

// ============================================================================
// Assistant CRUD Operations
// ============================================================================

/**
 * Get all assistants
 */
export async function getAssistants(
  activeOnly: boolean = true,
  schoolId?: string,
  accessToken?: string | null
): Promise<Assistant[]> {
  let url = `/api/v1/assistants?active_only=${activeOnly}`;
  if (schoolId) {
    url += `&school_id=${schoolId}`;
  }

  const response = await authGet(url, accessToken ?? null);

  if (!response.ok) {
    throw new Error(`Failed to fetch assistants: ${response.statusText}`);
  }

  const data = await response.json();
  return data.assistants;
}

/**
 * Search assistants by name or email
 */
export async function searchAssistants(query: string, accessToken?: string | null): Promise<Assistant[]> {
  if (query.length < 2) {
    return [];
  }

  const response = await authGet(
    `/api/v1/assistants/search?q=${encodeURIComponent(query)}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to search assistants: ${response.statusText}`);
  }

  const data = await response.json();
  return data.assistants;
}

/**
 * Get assistant by ID
 */
export async function getAssistant(assistantId: string, accessToken?: string | null): Promise<Assistant> {
  const response = await authGet(
    `/api/v1/assistants/${assistantId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch assistant: ${response.statusText}`);
  }

  const data = await response.json();
  return data.nurse;
}

/**
 * Create new assistant
 */
export async function createAssistant(request: CreateAssistantRequest, accessToken?: string | null): Promise<Assistant> {
  const response = await authPost(
    `/api/v1/assistants`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to create assistant: ${response.statusText}`);
  }

  const data = await response.json();
  return data.nurse;
}

/**
 * Update assistant
 */
export async function updateAssistant(
  assistantId: string,
  request: UpdateAssistantRequest,
  accessToken?: string | null
): Promise<Assistant> {
  const response = await authPut(
    `/api/v1/assistants/${assistantId}`,
    accessToken ?? null,
    request
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to update assistant: ${response.statusText}`);
  }

  const data = await response.json();
  return data.nurse;
}

/**
 * Deactivate assistant (soft delete)
 */
export async function deactivateAssistant(assistantId: string, accessToken?: string | null): Promise<Assistant> {
  const response = await authDelete(
    `/api/v1/assistants/${assistantId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to deactivate assistant: ${response.statusText}`);
  }

  const data = await response.json();
  return data.nurse;
}

/**
 * Get list of all active assistants (for sharing templates)
 */
export async function getAllAssistantsForSharing(accessToken?: string | null): Promise<AssistantListItem[]> {
  const response = await authGet(
    `/api/v1/assistants/list-all`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch assistants list: ${response.statusText}`);
  }

  const data = await response.json();
  return data.assistants || [];
}

// ============================================================================
// Assistant-Counsellor Association Operations
// ============================================================================

/**
 * Get counsellors linked to an assistant
 */
export async function getAssistantCounsellors(assistantId: string, accessToken?: string | null): Promise<AssistantCounsellor[]> {
  const response = await authGet(
    `/api/v1/assistants/${assistantId}/counsellors`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch assistant's counsellors: ${response.statusText}`);
  }

  const data = await response.json();
  return data.counsellors || [];
}

/**
 * Link assistant to a counsellor
 */
export async function linkAssistantToCounsellor(
  assistantId: string,
  counsellorId: string,
  accessToken?: string | null
): Promise<void> {
  const response = await authPost(
    `/api/v1/assistants/${assistantId}/counsellors/${counsellorId}`,
    accessToken ?? null,
    {}
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to link assistant to counsellor: ${response.statusText}`);
  }
}

/**
 * Unlink assistant from a counsellor
 */
export async function unlinkAssistantFromCounsellor(
  assistantId: string,
  counsellorId: string,
  accessToken?: string | null
): Promise<void> {
  const response = await authDelete(
    `/api/v1/assistants/${assistantId}/counsellors/${counsellorId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to unlink assistant from counsellor: ${response.statusText}`);
  }
}

// ============================================================================
// Assistant Template Operations
// ============================================================================

/**
 * Get templates accessible by an assistant
 */
export async function getAssistantTemplates(assistantId: string, accessToken?: string | null): Promise<AssistantTemplate[]> {
  const response = await authGet(
    `/api/v1/assistant-templates/accessible?assistant_id=${assistantId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch assistant templates: ${response.statusText}`);
  }

  const data = await response.json();
  return data.templates || [];
}

/**
 * Get the active template for an assistant
 */
export async function getAssistantActiveTemplate(assistantId: string, accessToken?: string | null): Promise<AssistantTemplate | null> {
  const response = await authGet(
    `/api/v1/assistant-templates/active?assistant_id=${assistantId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    if (response.status === 404) {
      return null;
    }
    throw new Error(`Failed to fetch assistant active template: ${response.statusText}`);
  }

  const data = await response.json();
  return data.template || null;
}

/**
 * Share template with assistants
 */
export interface ShareTemplateWithAssistantsResult {
  success: boolean;
  message: string;
  shared_count: number;
  failed_count: number;
  failures?: Array<{ assistant_id: string; error: string }>;
}

export async function shareTemplateWithAssistants(
  templateId: string,
  templateCode: string,
  assistantIds: string[],
  accessToken?: string | null
): Promise<ShareTemplateWithAssistantsResult> {
  const response = await authPost(
    `/api/v1/assistant-templates/share`,
    accessToken ?? null,
    {
      template_id: templateId,
      template_code: templateCode,
      assistant_ids: assistantIds,
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to share template with assistants: ${response.statusText}`);
  }

  return await response.json();
}

/**
 * Activate template for assistant
 */
export async function activateAssistantTemplate(
  assistantId: string,
  templateId: string,
  accessToken?: string | null
): Promise<{ success: boolean; is_active: boolean }> {
  const response = await authPost(
    `/api/v1/assistant-templates/activate`,
    accessToken ?? null,
    {
      assistant_id: assistantId,
      template_id: templateId,
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to activate assistant template: ${response.statusText}`);
  }

  return await response.json();
}

/**
 * Deactivate template for assistant
 */
export async function deactivateAssistantTemplate(
  assistantId: string,
  templateId: string,
  accessToken?: string | null
): Promise<{ success: boolean; is_active: boolean }> {
  const response = await authPost(
    `/api/v1/assistant-templates/deactivate`,
    accessToken ?? null,
    {
      assistant_id: assistantId,
      template_id: templateId,
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to deactivate assistant template: ${response.statusText}`);
  }

  return await response.json();
}

/**
 * Revoke assistant's access to a template
 */
export async function revokeAssistantTemplateAccess(
  assistantId: string,
  templateId: string,
  accessToken?: string | null
): Promise<void> {
  const response = await authDelete(
    `/api/v1/assistant-templates/revoke?assistant_id=${assistantId}&template_id=${templateId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to revoke assistant template access: ${response.statusText}`);
  }
}

/**
 * Validate if assistant has access to use a template
 */
export async function validateAssistantTemplateAccess(
  assistantId: string,
  templateId: string,
  accessToken?: string | null
): Promise<{ has_access: boolean }> {
  const response = await authGet(
    `/api/v1/assistant-templates/validate-access?assistant_id=${assistantId}&template_id=${templateId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to validate assistant template access: ${response.statusText}`);
  }

  return await response.json();
}

/**
 * Get assistants who have access to a specific template (for sharing modal)
 */
export async function getTemplateAssistantShares(
  templateId: string,
  accessToken?: string | null
): Promise<Array<{ assistant_id: string; is_active: boolean }>> {
  const response = await authGet(
    `/api/v1/assistant-templates/template-shares/${templateId}`,
    accessToken ?? null
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch template assistant shares: ${response.statusText}`);
  }

  const data = await response.json();
  return data.shares || [];
}
