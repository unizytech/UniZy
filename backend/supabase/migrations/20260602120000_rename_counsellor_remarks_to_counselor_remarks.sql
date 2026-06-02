-- Rename the COUNSELLOR_REMARKS segment to COUNSELOR_REMARKS (American) so its auto-derived
-- camelCase output key becomes `counselorRemarks`, matching the careerzilla response contract
-- (references/updated_meeting_response_structure.json: key "counselorRemarks", label
-- "Additional Remarks (Counselors Only)"). The output key is _to_camel_case(segment_code) with no
-- code-side literals, so the rename flips the key everywhere (write schema + all read parsers).
--
-- Safe: the config junctions reference segment_definitions by segment_id (UUID), not segment_code
-- (segment_code is non-unique), so no FK is affected. The denormalised segment_code copies in the
-- two config junctions are updated too. Historical extraction_segments / segment_embeddings rows are
-- intentionally LEFT on the old code (they are past data, not config).
--
-- AFTER this migration, regenerate the CAREER_DISCUSSION template's assembled_schema_json +
-- assembled_full_prompt via template_assembly_service so the schema key becomes counselorRemarks.

begin;

update public.segment_definitions
   set segment_code = 'COUNSELOR_REMARKS',
       segment_name = 'Additional Remarks (Counselors Only)',
       updated_at   = now()
 where segment_code = 'COUNSELLOR_REMARKS';

update public.consultation_type_segments
   set segment_code = 'COUNSELOR_REMARKS'
 where segment_code = 'COUNSELLOR_REMARKS';

update public.template_segments
   set segment_code = 'COUNSELOR_REMARKS'
 where segment_code = 'COUNSELLOR_REMARKS';

commit;
