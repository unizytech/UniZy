-- Add an external-id mapping column to counsellors and assistants so callers whose own system uses
-- bigint ids can address these entities by their external id instead of the internal UUID. The
-- /recording/start endpoint resolves an incoming counsellor_id/assistant_id as EITHER the internal
-- UUID or this external_id, mapping to the internal UUID (mirrors how students.student_id already
-- works as an external identifier). No internal PKs change. external_id is nullable (existing rows
-- stay NULL until provisioned) and unique among non-null values.

alter table public.counsellors add column if not exists external_id bigint;
alter table public.assistants  add column if not exists external_id bigint;

create unique index if not exists counsellors_external_id_key
  on public.counsellors (external_id) where external_id is not null;
create unique index if not exists assistants_external_id_key
  on public.assistants (external_id) where external_id is not null;

comment on column public.counsellors.external_id is
  'Optional caller-system (bigint) identifier for this counsellor; resolved to the internal UUID by /recording/start.';
comment on column public.assistants.external_id is
  'Optional caller-system (bigint) identifier for this assistant; resolved to the internal UUID by /recording/start.';
