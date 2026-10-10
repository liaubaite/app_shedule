-- Vykdykite Supabase SQL Editor tik vieną kartą.
-- Tik serveriui prieinama lentelė; jokia prieiga per anon / authenticated roles.
create table if not exists public.app_state (
  id text primary key,
  payload text not null
);
alter table public.app_state enable row level security;
revoke all on public.app_state from anon, authenticated;
-- RLS politika niekam nesuteikiama. Naudoti tik slaptą serverio service_role raktą.
