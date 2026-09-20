-- Ejecuta esto UNA VEZ en tu proyecto de Supabase: Panel izquierdo > SQL Editor >
-- New query > pega todo esto > Run.

create table if not exists exam_configs (
  nom_id text primary key,
  title text not null,
  approve_operator text not null default '>=',
  approve_threshold integer not null default 8,
  questions jsonb not null,
  options jsonb not null,
  answer_key jsonb not null,
  created_at timestamptz default now()
);

-- Seguridad: esta tabla solo la toca la app usando la llave "service role"
-- (nunca la llave pública/anon), así que la protegemos activando RLS sin
-- ninguna política -- eso bloquea cualquier acceso que no sea con esa llave.
alter table exam_configs enable row level security;
