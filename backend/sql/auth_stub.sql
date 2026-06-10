-- Auth schema stub for local dev and CI (non-Supabase Postgres).
-- In production Supabase, auth.users and auth.uid() are provided by the
-- platform; this file MUST NOT be applied to production.
--
-- auth.uid() reads the app.current_user_id GUC so tests can do:
--   SET LOCAL "app.current_user_id" = '<uuid>';
-- to simulate a logged-in user without a real JWT.

CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email      text UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION auth.uid()
    RETURNS uuid
    LANGUAGE sql STABLE
AS $$
    SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid
$$;
