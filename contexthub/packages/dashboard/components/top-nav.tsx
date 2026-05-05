"use client";

import { useEffect, useState } from "react";
import {
  getSupabaseSession,
  isSupabaseAuthConfigured,
  onSupabaseAuthStateChange,
  signOutSupabase
} from "@/lib/supabase";

export function TopNav() {
  const [sessionEmail, setSessionEmail] = useState<string | null>(null);
  const supabaseEnabled = isSupabaseAuthConfigured();

  useEffect(() => {
    if (!supabaseEnabled) return;
    getSupabaseSession().then((session) => setSessionEmail(session?.user?.email ?? null));
    const unsubscribe = onSupabaseAuthStateChange((session) => {
      setSessionEmail(session?.user?.email ?? null);
    });
    return unsubscribe;
  }, [supabaseEnabled]);

  async function signOut() {
    try {
      await signOutSupabase();
    } catch {
      // ignore
    }
  }

  const initial = (sessionEmail || "?").charAt(0).toUpperCase();

  return (
    <header className="top-nav">
      <div className="brand">
        <span className="brand-mark">C</span>
        <span className="brand-name">ContextHub</span>
      </div>

      {supabaseEnabled && sessionEmail ? (
        <div className="auth-controls">
          <div className="user-chip">
            <span className="user-avatar" title={sessionEmail}>{initial}</span>
            <span>{sessionEmail}</span>
          </div>
          <button className="link-btn" onClick={signOut} type="button">
            Sign out
          </button>
        </div>
      ) : null}
    </header>
  );
}
