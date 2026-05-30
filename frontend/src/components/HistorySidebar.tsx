"use client";

import type { ConversationSummary } from "@/lib/api";

// Left sidebar: persistent conversation history (transparent surface).
export default function HistorySidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
}: {
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  return (
    <aside className="flex h-full flex-col bg-transparent">
      <div className="px-3 pt-4">
        <button
          onClick={onNew}
          className="flex w-full items-center gap-2 rounded-full bg-white/70 px-4 py-2.5 text-sm font-medium text-ink ring-1 ring-black/5 backdrop-blur transition hover:bg-white"
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 5v14M5 12h14" strokeLinecap="round" />
          </svg>
          New conversation
        </button>
      </div>

      <div className="px-4 pb-2 pt-5">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
          Recent
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {conversations.length === 0 && (
          <p className="px-2 text-xs text-muted">No conversations yet.</p>
        )}
        {conversations.map((c) => {
          const active = c.id === activeId;
          return (
            <button
              key={c.id}
              onClick={() => onSelect(c.id)}
              className={`mb-0.5 flex w-full items-center gap-2 truncate rounded-xl px-3 py-2 text-left text-sm transition ${
                active
                  ? "bg-white/80 text-ink ring-1 ring-black/5"
                  : "text-muted hover:bg-white/50 hover:text-ink"
              }`}
              title={c.title}
            >
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 shrink-0 opacity-60" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="truncate">{c.title}</span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
