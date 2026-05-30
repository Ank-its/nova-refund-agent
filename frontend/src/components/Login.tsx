"use client";

import { useState } from "react";
import { login } from "@/lib/api";
import type { Session } from "@/lib/types";

const DEMO_ACCOUNTS = [
  { u: "alice", label: "Customer · clean approval" },
  { u: "bob", label: "Customer · high-value ($1299)" },
  { u: "carol", label: "Customer · final sale" },
  { u: "dave", label: "Customer · velocity abuse" },
  { u: "mallory", label: "Customer · injection target" },
  { u: "admin", label: "Admin · telemetry only" },
  { u: "superuser", label: "Super-user · chat + telemetry" },
];

export default function Login({ onLogin }: { onLogin: (s: Session) => void }) {
  const [username, setUsername] = useState("alice");
  const [password, setPassword] = useState("demo1234");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogin(await login(username, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-b from-soft to-[#e9ebee] px-4">
      <div className="w-full max-w-md">
        <div className="mb-7 text-center">
          <div className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-ink text-xl font-semibold text-white shadow-lg shadow-black/10">
            W
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Worknoon
          </h1>
          <p className="mt-1 text-sm text-muted">Sign in to continue</p>
        </div>

        <form
          onSubmit={submit}
          className="rounded-3xl border border-line bg-white p-7 shadow-xl shadow-black/[0.05]"
        >
          <label className="mb-1.5 block text-xs font-medium text-muted">
            Username
          </label>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mb-4 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none transition focus:border-ink"
            autoComplete="username"
          />
          <label className="mb-1.5 block text-xs font-medium text-muted">
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mb-4 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none transition focus:border-ink"
            autoComplete="current-password"
          />
          {error && (
            <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-reject ring-1 ring-red-100">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-xl bg-ink py-3 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="mt-5 rounded-3xl border border-line bg-white p-5">
          <p className="mb-3 text-xs font-medium text-muted">
            Demo accounts · password{" "}
            <code className="rounded bg-soft px-1.5 py-0.5 text-ink">demo1234</code>
          </p>
          <div className="flex flex-wrap gap-1.5">
            {DEMO_ACCOUNTS.map((a) => (
              <button
                key={a.u}
                onClick={() => {
                  setUsername(a.u);
                  setPassword("demo1234");
                }}
                title={a.label}
                className={`rounded-full border px-3 py-1 text-xs transition ${
                  username === a.u
                    ? "border-ink bg-ink text-white"
                    : "border-line text-ink hover:bg-soft"
                }`}
              >
                {a.u}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
