"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  getSupabaseSession,
  isSupabaseAuthConfigured,
  onSupabaseAuthStateChange,
  signInWithMagicLink,
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
  const [authEmail, setAuthEmail] = useState("");
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

  async function sendMagicLink() {
    if (!authEmail.trim()) {
      setAuthStatus("Enter an email address first.");
      return;
    }
    setAuthStatus("Sending magic link...");
    try {
      await signInWithMagicLink(authEmail.trim());
      setAuthStatus("Check your email for a sign-in link.");
    } catch (err) {
      setAuthStatus(err instanceof Error ? err.message : "Unable to send magic link.");
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
            <>
              <input
                value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)}
                placeholder="you@example.com"
              />
              <button className="button secondary" onClick={sendMagicLink} type="button">
                Email sign-in link
              </button>
            </>
          )
        ) : (
          <span className="muted">Supabase auth not configured</span>
        )}
      </div>
      {authStatus ? <span className="muted" style={{ marginLeft: 8 }}>{authStatus}</span> : null}
    </header>
  );
}
