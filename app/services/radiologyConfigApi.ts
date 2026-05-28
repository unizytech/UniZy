/**
 * Radiology Config API client
 *
 * Wraps backend /api/v1/radiology endpoints for plan library, toxicity library,
 * standard texts, and the read-only examination segment viewer.
 */

import { authDelete, authGet, authPost, authPut } from '@lib/apiClient';

export interface PlanItem {
  id: string;
  template_id: string;
  plan_code: string;
  plan_name: string;
  rt_intent: string | null;
  rt_indication: string | null;
  rt_dose_gy: string | null;
  rt_fractions: string | null;
  rt_dose_per_fraction_gy: string | null;
  rt_weeks: string | null;
  rt_technique: string | null;
  concurrent_systemic_therapy: string | null;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PlanItemPayload {
  plan_code?: string;
  plan_name?: string;
  rt_intent?: string | null;
  rt_indication?: string | null;
  rt_dose_gy?: string | null;
  rt_fractions?: string | null;
  rt_dose_per_fraction_gy?: string | null;
  rt_weeks?: string | null;
  rt_technique?: string | null;
  concurrent_systemic_therapy?: string | null;
  display_order?: number;
  is_active?: boolean;
}

export interface ToxicityItem {
  id: string;
  template_id: string;
  toxicity_code: string;
  phase: 'early' | 'late';
  text: string;
  conditional_trigger: string | null;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ToxicityItemPayload {
  toxicity_code?: string;
  phase?: 'early' | 'late';
  text?: string;
  conditional_trigger?: string | null;
  display_order?: number;
  is_active?: boolean;
}

export interface StandardTextItem {
  id: string;
  template_id: string;
  key: string;
  label: string | null;
  text: string;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface StandardTextPayload {
  key?: string;
  label?: string | null;
  text?: string;
  display_order?: number;
  is_active?: boolean;
}

export interface ExaminationSegment {
  segment_code: string;
  segment_name: string | null;
  prompt_section_text: string | null;
  schema_definition_json: Record<string, unknown> | null;
}

type Token = string | null;

async function unwrap<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail || fallback);
  }
  return res.json() as Promise<T>;
}

const base = (templateId: string) => `/api/v1/radiology/templates/${templateId}`;

// ---- Plan library --------------------------------------------------------

export async function listPlanLibrary(templateId: string, token: Token): Promise<PlanItem[]> {
  const res = await authGet(`${base(templateId)}/plan-library`, token);
  const data = await unwrap<{ items: PlanItem[] }>(res, 'Failed to load plan library');
  return data.items || [];
}

export async function createPlanItem(templateId: string, token: Token, payload: PlanItemPayload): Promise<PlanItem> {
  const res = await authPost(`${base(templateId)}/plan-library`, token, payload);
  const data = await unwrap<{ item: PlanItem }>(res, 'Failed to create plan item');
  return data.item;
}

export async function updatePlanItem(templateId: string, itemId: string, token: Token, payload: PlanItemPayload): Promise<PlanItem> {
  const res = await authPut(`${base(templateId)}/plan-library/${itemId}`, token, payload);
  const data = await unwrap<{ item: PlanItem }>(res, 'Failed to update plan item');
  return data.item;
}

export async function deletePlanItem(templateId: string, itemId: string, token: Token): Promise<void> {
  const res = await authDelete(`${base(templateId)}/plan-library/${itemId}`, token);
  await unwrap<{ item: PlanItem }>(res, 'Failed to delete plan item');
}

// ---- Toxicity library ----------------------------------------------------

export async function listToxicityLibrary(
  templateId: string,
  token: Token,
  phase?: 'early' | 'late',
): Promise<ToxicityItem[]> {
  const qs = phase ? `?phase=${phase}` : '';
  const res = await authGet(`${base(templateId)}/toxicity-library${qs}`, token);
  const data = await unwrap<{ items: ToxicityItem[] }>(res, 'Failed to load toxicity library');
  return data.items || [];
}

export async function createToxicityItem(templateId: string, token: Token, payload: ToxicityItemPayload): Promise<ToxicityItem> {
  const res = await authPost(`${base(templateId)}/toxicity-library`, token, payload);
  const data = await unwrap<{ item: ToxicityItem }>(res, 'Failed to create toxicity item');
  return data.item;
}

export async function updateToxicityItem(templateId: string, itemId: string, token: Token, payload: ToxicityItemPayload): Promise<ToxicityItem> {
  const res = await authPut(`${base(templateId)}/toxicity-library/${itemId}`, token, payload);
  const data = await unwrap<{ item: ToxicityItem }>(res, 'Failed to update toxicity item');
  return data.item;
}

export async function deleteToxicityItem(templateId: string, itemId: string, token: Token): Promise<void> {
  const res = await authDelete(`${base(templateId)}/toxicity-library/${itemId}`, token);
  await unwrap<{ item: ToxicityItem }>(res, 'Failed to delete toxicity item');
}

// ---- Standard texts ------------------------------------------------------

export async function listStandardTexts(templateId: string, token: Token): Promise<StandardTextItem[]> {
  const res = await authGet(`${base(templateId)}/standard-texts`, token);
  const data = await unwrap<{ items: StandardTextItem[] }>(res, 'Failed to load standard texts');
  return data.items || [];
}

export async function createStandardText(templateId: string, token: Token, payload: StandardTextPayload): Promise<StandardTextItem> {
  const res = await authPost(`${base(templateId)}/standard-texts`, token, payload);
  const data = await unwrap<{ item: StandardTextItem }>(res, 'Failed to create standard text');
  return data.item;
}

export async function updateStandardText(templateId: string, itemId: string, token: Token, payload: StandardTextPayload): Promise<StandardTextItem> {
  const res = await authPut(`${base(templateId)}/standard-texts/${itemId}`, token, payload);
  const data = await unwrap<{ item: StandardTextItem }>(res, 'Failed to update standard text');
  return data.item;
}

export async function deleteStandardText(templateId: string, itemId: string, token: Token): Promise<void> {
  const res = await authDelete(`${base(templateId)}/standard-texts/${itemId}`, token);
  await unwrap<{ item: StandardTextItem }>(res, 'Failed to delete standard text');
}

// ---- Examination viewer --------------------------------------------------

export async function getExaminationSegment(templateId: string, token: Token): Promise<ExaminationSegment | null> {
  const res = await authGet(`${base(templateId)}/examination-segment`, token);
  if (res.status === 404) return null;
  return unwrap<ExaminationSegment>(res, 'Failed to load examination segment');
}
