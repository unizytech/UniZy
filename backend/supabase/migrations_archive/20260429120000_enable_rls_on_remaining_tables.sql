-- Enable RLS + add "Service role full access" policy on tables that were missing it.
-- Idempotent: each block runs only if the table exists in the target DB
-- (some tables — customers, financial_*, app_settings — exist only in main-dev).
-- Re-runs are safe: DROP POLICY IF EXISTS + CREATE POLICY.

DO $$
DECLARE
  t text;
  tables text[] := ARRAY[
    'app_settings',
    'bill_line_items',
    'bills',
    'customers',
    'doctor_doctor_patients',
    'extraction_accuracy_metrics',
    'extraction_edit_history',
    'financial_extractions',
    'financial_intent_analysis',
    'financial_intervention_outcomes',
    'financial_interventions',
    'models_master',
    'procedure_fee_master',
    'radiology_plan_library',
    'radiology_toxicity_library',
    'refresh_tokens',
    'room_rate_master',
    'template_standard_texts'
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    IF EXISTS (
      SELECT 1 FROM pg_tables
      WHERE schemaname = 'public' AND tablename = t
    ) THEN
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
      EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON public.%I', t);
      EXECUTE format(
        'CREATE POLICY "Service role full access" ON public.%I FOR ALL TO service_role USING (true) WITH CHECK (true)',
        t
      );
    END IF;
  END LOOP;
END$$;
