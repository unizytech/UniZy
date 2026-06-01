-- Phase 7G: rename the remaining "distinct" entity-reference columns to school vocabulary.
-- These are columns that reference doctors/patients/hospitals/nurses by meaning but were not part
-- of the *_id FK families renamed in 7A-7D (e.g. denormalised counts, flags, list columns).
-- Behaviour-neutral metadata rename.

begin;

alter table public.api_clients                 rename column allowed_doctor_ids to allowed_counsellor_ids;
alter table public.clinical_conditions         rename column patient_education to student_education;
alter table public.consultation_insights       rename column patient_signals to student_signals;
alter table public.consultation_types          rename column visible_to_doctors to visible_to_counsellors;
alter table public.consultation_types          rename column visible_to_hospitals to visible_to_schools;
alter table public.doctor_layer_preferences    rename column enable_doctor_practice_layer to enable_counsellor_practice_layer;
alter table public.doctor_layer_preferences    rename column enable_hospital_intelligence_layer to enable_school_intelligence_layer;
alter table public.doctor_layer_preferences    rename column weight_doctor_practice to weight_counsellor_practice;
alter table public.doctor_layer_preferences    rename column weight_hospital_intelligence to weight_school_intelligence;
alter table public.extraction_accuracy_metrics rename column doctor_additions_count to counsellor_additions_count;
alter table public.extraction_accuracy_metrics rename column total_words_doctor_edit to total_words_counsellor_edit;
alter table public.hospital_specialty_patterns rename column doctor_count to counsellor_count;
alter table public.investigation_match_log     rename column matched_hospital_investigation_id to matched_school_investigation_id;
alter table public.medicine_match_log          rename column matched_hospital_medicine_id to matched_school_medicine_id;
alter table public.qa_engine_settings          rename column allow_cross_doctor_search to allow_cross_counsellor_search;
alter table public.recording_sessions          rename column patient_identifier to student_identifier;
alter table public.specialty_benchmarks        rename column total_doctors to total_counsellors;
alter table public.specialty_benchmarks        rename column total_hospitals to total_schools;
alter table public.triage_suggestion_log       rename column patient_context_applied to student_context_applied;

notify pgrst, 'reload schema';

commit;
