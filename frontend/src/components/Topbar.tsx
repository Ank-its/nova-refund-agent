"use client";

import type { Role } from "@/lib/types";

export default function Topbar({
  username,
  role,
  canViewAdmin,
  adminOpen,
  onToggleAdmin,
  onLogout,
}: {
  username: string;
  role: Role;
  canViewAdmin: boolean;
  adminOpen: boolean;
  onToggleAdmin: () => void;
  onLogout: () => void;
}) {
  const initial = username.charAt(0).toUpperCase();
  return (
    <header className="flex items-center justify-between border-b border-black/5 bg-white/60 px-5 py-3 backdrop-blur">
      <div className="flex items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-ink text-sm font-semibold text-white">
          W
        </div>
        <span className="text-sm font-semibold tracking-tight text-ink">
          Worknoon
        </span>
      </div>

      <div className="flex items-center gap-3">
        {canViewAdmin && (
          <button
            onClick={onToggleAdmin}
            className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-medium transition ${
              adminOpen
                ? "border-ink bg-ink text-white"
                : "border-black/10 bg-white/70 text-ink hover:bg-white"
            }`}
            title="Toggle the admin telemetry panel"
          >
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 3v18h18" strokeLinecap="round" />
              <path d="M7 14l3-3 3 3 4-5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {adminOpen ? "Hide telemetry" : "Telemetry"}
          </button>
        )}

        <div className="flex items-center gap-2.5 rounded-xl border border-black/10 bg-white/70 py-1 pl-1 pr-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-soft text-xs font-semibold text-ink">
            {initial}
          </div>
          <div className="text-right leading-tight">
            <div className="text-xs font-medium text-ink">{username}</div>
            <div className="text-[10px] uppercase tracking-wide text-muted">
              {role}
            </div>
          </div>
          <button
            onClick={onLogout}
            className="ml-1 rounded-lg p-1.5 text-muted transition hover:bg-soft hover:text-ink"
            title="Sign out"
            aria-label="Sign out"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>
    </header>
  );
}
