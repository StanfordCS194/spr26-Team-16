"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  getSupabaseSession,
  isSupabaseAuthConfigured,
  onSupabaseAuthStateChange,
  signInWithGoogle,
  signOutSupabase
} from "@/lib/supabase";

const navItems = [
  { href: "/", label: "Overview" },
  { href: "/workspaces", label: "Workspaces" },
  { href: "/tokens", label: "Tokens" },
  { href: "/search", label: "Search" }
];

export function TopNav() {
  const pathname = usePathname();
  const [sessionEmail, setSessionEmail] = useState<string | null>(null);
  const [authStatus, setAuthStatus] = useState<string | null>(null);
  const supabaseEnabled = isSupabaseAuthConfigured();

  useEffect(() => {
    if (!supabaseEnabled) return;
    getSupabaseSession().then((session) => setSessionEmail(session?.user?.email ?? null));
    const unsubscribe = onSupabaseAuthStateChange((session) => {
      setSessionEmail(session?.user?.email ?? null);
    });
    return unsubscribe;
  }, [supabaseEnabled]);

  async function signInGoogle() {
    setAuthStatus("Redirecting to Google...");
    try {
      await signInWithGoogle();
    } catch (err) {
      setAuthStatus(err instanceof Error ? err.message : "Unable to sign in with Google.");
    }
  }

  async function signOut() {
    setAuthStatus("Signing out...");
    try {
      await signOutSupabase();
      setAuthStatus("Signed out.");
    } catch (err) {
      setAuthStatus(err instanceof Error ? err.message : "Unable to sign out.");
    }
  }

  return (
    <header className="top-nav">
      <div className="brand">ContextHub Dashboard</div>
      <nav className="links">
        {navItems.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              className={`link ${active ? "link-active" : ""}`}
              key={item.href}
              href={item.href}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="auth-controls">
        {supabaseEnabled ? (
          sessionEmail ? (
            <>
              <span className="muted">Signed in as {sessionEmail}</span>
              <button className="button secondary" onClick={signOut} type="button">
                Sign out
              </button>
            </>
          ) : (
            <button className="button" onClick={signInGoogle} type="button">
              Sign in with Google
            </button>
          )
        ) : (
          <span className="muted">Supabase auth not configured</span>
        )}
      </div>
      {authStatus ? <span className="muted" style={{ marginLeft: 8 }}>{authStatus}</span> : null}
    </header>
  );
}
