-- Phase 7D: rename column doctor_id -> counsellor_id (counsellor entity column family) plus
-- the doctor_ids array and the linked/source/target_doctor_id variants.
--
-- Final per-entity DB+code cutover slice (healthcare->schools). doctor_id is purely a child FK
-- (it is NOT a column on any entity table), so no compat view exposes it and none needs
-- recreation here. After this slice all four entities are accessed via base-table names; the
-- backward-compat views (hospitals/doctors/patients/nurses) become unused and are dropped in a
-- follow-up (Phase E).
--
-- FK constraints/indexes auto-follow the rename (metadata-only). No RLS policy references
-- doctor_id (verified). Columns that merely CONTAIN "doctor" but are a different concept
-- (doctor_name, allowed_doctor_ids, visible_to_doctors, doctor_count, ...) are intentionally NOT
-- renamed. Junction table NAMES (doctor_templates, doctor_medicines, nurse_doctors, ...) are kept.

begin;

-- 1. doctor_id -> counsellor_id on every base table that carries it.
alter table public.allied_health_needs                    rename column doctor_id to counsellor_id;
alter table public.api_client_usage                       rename column doctor_id to counsellor_id;
alter table public.bills                                  rename column doctor_id to counsellor_id;
alter table public.care_quality_risk                      rename column doctor_id to counsellor_id;
alter table public.clinical_severity_assessments          rename column doctor_id to counsellor_id;
alter table public.consultation_insights                  rename column doctor_id to counsellor_id;
alter table public.doctor_doctor_patients                 rename column doctor_id to counsellor_id;
alter table public.doctor_investigations                  rename column doctor_id to counsellor_id;
alter table public.doctor_layer_preferences               rename column doctor_id to counsellor_id;
alter table public.doctor_medicines                       rename column doctor_id to counsellor_id;
alter table public.doctor_practice_styles                 rename column doctor_id to counsellor_id;
alter table public.doctor_segment_configurations_backup_014 rename column doctor_id to counsellor_id;
alter table public.doctor_templates                       rename column doctor_id to counsellor_id;
alter table public.extraction_accuracy_metrics            rename column doctor_id to counsellor_id;
alter table public.extraction_embeddings                  rename column doctor_id to counsellor_id;
alter table public.followup_tracking                      rename column doctor_id to counsellor_id;
alter table public.investigation_list_uploads             rename column doctor_id to counsellor_id;
alter table public.investigation_match_log                rename column doctor_id to counsellor_id;
alter table public.llm_usage_log                          rename column doctor_id to counsellor_id;
alter table public.medical_extractions                    rename column doctor_id to counsellor_id;
alter table public.medicine_list_uploads                  rename column doctor_id to counsellor_id;
alter table public.medicine_match_log                     rename column doctor_id to counsellor_id;
alter table public.nurse_doctors                          rename column doctor_id to counsellor_id;
alter table public.other_clinical_needs                   rename column doctor_id to counsellor_id;
alter table public.patient_dropoff_risk                   rename column doctor_id to counsellor_id;
alter table public.phi_audit_log                          rename column doctor_id to counsellor_id;
alter table public.qa_query_history                       rename column doctor_id to counsellor_id;
alter table public.realtime_extraction_responses          rename column doctor_id to counsellor_id;
alter table public.recording_sessions                     rename column doctor_id to counsellor_id;
alter table public.segment_definitions                    rename column doctor_id to counsellor_id;
alter table public.segment_embeddings                     rename column doctor_id to counsellor_id;
alter table public.templates                              rename column doctor_id to counsellor_id;
alter table public.triage_feedback                        rename column doctor_id to counsellor_id;
alter table public.triage_suggestion_log                  rename column doctor_id to counsellor_id;

-- 2. doctor_ids array on the student entity.
alter table public.students rename column doctor_ids to counsellor_ids;

-- 3. Variant FK columns.
alter table public.doctor_doctor_patients rename column linked_doctor_id to linked_counsellor_id;
alter table public.patient_sharing        rename column source_doctor_id to source_counsellor_id;
alter table public.patient_sharing        rename column target_doctor_id to target_counsellor_id;

notify pgrst, 'reload schema';

commit;
