import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";

let supabaseClient: SupabaseClient | null | undefined;

export function isSupabaseAuthConfigured() {
  return Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);
}

export function getSupabaseClient() {
  if (supabaseClient !== undefined) return supabaseClient;
  if (!isSupabaseAuthConfigured()) {
    supabaseClient = null;
    return supabaseClient;
  }
  supabaseClient = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL as string,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY as string,
    {
      auth: {
        flowType: "pkce",
        detectSessionInUrl: true
      }
    }
  );
  return supabaseClient;
}

export async function getSupabaseAccessToken() {
  const client = getSupabaseClient();
  if (!client) return null;
  const { data } = await client.auth.getSession();
  return data.session?.access_token ?? null;
}

export async function getSupabaseSession() {
  const client = getSupabaseClient();
  if (!client) return null;
  const { data } = await client.auth.getSession();
  return data.session;
}

export async function signInWithMagicLink(email: string) {
  const client = getSupabaseClient();
  if (!client) throw new Error("Supabase auth is not configured.");
  const { error } = await client.auth.signInWithOtp({ email });
  if (error) throw error;
}

/**
 * Browser redirect flow. After Google approves, Supabase redirects back to
 * `redirectTo` (your dashboard); the client picks up the session from the URL.
 */
export async function signInWithGoogle() {
  const client = getSupabaseClient();
  if (!client) throw new Error("Supabase auth is not configured.");
  if (typeof window === "undefined") {
    throw new Error("Google sign-in must run in the browser.");
  }
  const { error } = await client.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: `${window.location.origin}/`
    }
  });
  if (error) throw error;
}

export async function signOutSupabase() {
  const client = getSupabaseClient();
  if (!client) return;
  const { error } = await client.auth.signOut();
  if (error) throw error;
}

export function onSupabaseAuthStateChange(callback: (session: Session | null) => void) {
  const client = getSupabaseClient();
  if (!client) return () => undefined;
  const { data } = client.auth.onAuthStateChange((_event, session) => callback(session));
  return () => data.subscription.unsubscribe();
}
