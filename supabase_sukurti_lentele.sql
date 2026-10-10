-- Supabase Dashboard -> SQL Editor -> Run.
-- Saugi pakartotinai vykdoma lentelės kūrimo ir teisių konfigūracija.
-- NIEKO netrina ir nekeičia jau išsaugotų duomenų.
create table if not exists public.app_state (
  id text primary key,
  payload text not null
);

alter table public.app_state enable row level security;

-- API pasiekiama tik serveriniu Supabase slaptu raktu,
-- kuris veikia su service_role teisėmis. Nenaudoti anon/publishable!
grant usage on schema public to service_role;
grant select, insert, update, delete on table public.app_state to service_role;
revoke all on table public.app_state from anon, authenticated;
