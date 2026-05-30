"use client";

import { useEffect, useState } from "react";
import Dashboard from "@/components/Dashboard";
import Login from "@/components/Login";
import type { Session } from "@/lib/types";

const STORAGE_KEY = "worknoon_session";

export default function Home() {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  // Restore session from localStorage on first paint.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setSession(JSON.parse(raw) as Session);
    } catch {
      // ignore
    }
    setReady(true);
  }, []);

  function handleLogin(s: Session) {
    setSession(s);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  }

  function handleLogout() {
    setSession(null);
    localStorage.removeItem(STORAGE_KEY);
  }

  if (!ready) return null;
  if (!session) return <Login onLogin={handleLogin} />;
  return <Dashboard session={session} onLogout={handleLogout} />;
}
