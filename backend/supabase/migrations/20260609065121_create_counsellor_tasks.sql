-- Counsellor TODO / Tasks
--
-- Until now, the actionable tasks a counsellor assigns lived only inside the extraction JSON
-- (the TASKS segment of extractions.original_extraction_json / edited_extraction_json). There was
-- no place for a counsellor to independently create, edit or delete their own to-do items. This
-- table backs the counsellor-tasks CRUD APIs.
--
-- Two flavours of task share one table:
--   * Per-student task   -> student_id IS NOT NULL (assigned to a specific student)
--   * Personal to-do     -> student_id IS NULL     (the counsellor's own private item)
--
-- Fields mirror the TASKS extraction segment so tasks can later be seeded from an extraction
-- (source_extraction_id points back to where an auto-created task came from; NULL = manually added).
-- Deletes are soft (is_active = false), matching how counsellors/templates are removed elsewhere.

create table if not exists public.counsellor_tasks (
    id                   uuid primary key default gen_random_uuid(),
    counsellor_id        uuid not null references public.counsellors(id) on delete cascade,
    student_id           uuid references public.students(id) on delete set null,
    source_extraction_id uuid references public.extractions(id) on delete set null,

    task_name            varchar(300) not null,
    task_details         text,
    task_type            varchar(20) not null default 'Once'
                            check (task_type in ('Once', 'Daily', 'Weekly', 'Monthly')),
    start_date           date,
    end_date             date,
    bucket_id            integer,
    duration_in_minutes  integer,
    task_category        varchar(200),
    task_file_resource   varchar(500),
    requires_approval    boolean not null default false,
    status               varchar(20) not null default 'open'
                            check (status in ('open', 'in_progress', 'done', 'cancelled')),

    external_id          bigint,  -- optional caller-system (bigint) id, mirrors counsellors.external_id

    is_active            boolean not null default true,
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now()
);

create index if not exists counsellor_tasks_counsellor_id_idx
    on public.counsellor_tasks (counsellor_id);
create index if not exists counsellor_tasks_student_id_idx
    on public.counsellor_tasks (student_id);
create index if not exists counsellor_tasks_status_idx
    on public.counsellor_tasks (status);
create index if not exists counsellor_tasks_active_idx
    on public.counsellor_tasks (counsellor_id, is_active);
create unique index if not exists counsellor_tasks_external_id_key
    on public.counsellor_tasks (external_id) where external_id is not null;

comment on table public.counsellor_tasks is
    'Counsellor to-do items / assigned tasks. student_id NULL = personal to-do; NOT NULL = per-student task. Mirrors the TASKS extraction segment.';
comment on column public.counsellor_tasks.source_extraction_id is
    'Extraction this task was seeded from (TASKS segment); NULL when the counsellor created it manually.';
comment on column public.counsellor_tasks.external_id is
    'Optional caller-system (bigint) identifier for this task; unique among non-null values.';
