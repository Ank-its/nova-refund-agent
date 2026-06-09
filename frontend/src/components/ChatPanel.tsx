"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatMessage, Decision } from "@/lib/types";

// The assistant's persona — a neutral, robotic-but-human name. Not "refund"
// branded: it's a general assistant that happens to help with returns.
const ASSISTANT_NAME = "Nova";

const BADGE: Record<Decision, { text: string; cls: string; dot: string }> = {
  approved: {
    text: "Approved",
    cls: "bg-green-50 text-approve ring-1 ring-green-100",
    dot: "bg-approve",
  },
  rejected: {
    text: "Not eligible",
    cls: "bg-red-50 text-reject ring-1 ring-red-100",
    dot: "bg-reject",
  },
  pending_review: {
    text: "Sent for human review",
    cls: "bg-amber-50 text-review ring-1 ring-amber-100",
    dot: "bg-review",
  },
};

function Avatar() {
  return (
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink text-[11px] font-semibold text-white">
      {ASSISTANT_NAME.charAt(0)}
    </div>
  );
}

function DecisionBadge({ decision }: { decision: Decision }) {
  const b = BADGE[decision];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${b.cls}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${b.dot}`} />
      {b.text}
    </span>
  );
}

function Reasoning({ steps }: { steps: string[] }) {
  const [open, setOpen] = useState(false);
  if (!steps.length) return null;
  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs font-medium text-muted transition hover:text-ink"
      >
        <svg
          viewBox="0 0 24 24"
          className={`h-3 w-3 transition-transform ${open ? "rotate-90" : ""}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
        >
          <path d="M9 18l6-6-6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Reasoning · {steps.length} steps
      </button>
      {open && (
        <ol className="mt-2 space-y-1 border-l border-line pl-3">
          {steps.map((s, i) => (
            <li key={i} className="text-xs text-muted">
              {s}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// While awaiting a reply: a typing indicator (dots) when there are no step
// labels yet, or the streamed tool-progress labels during a refund flow.
function Thinking({ steps }: { steps: string[] }) {
  const current = steps[steps.length - 1];
  if (!current) {
    return (
      <div className="flex items-start gap-2.5 animate-rise">
        <Avatar />
        <div className="rounded-2xl rounded-bl-md bg-white/70 px-4 py-3.5 ring-1 ring-black/5 backdrop-blur">
          <span className="flex gap-1" aria-label="Nova is typing">
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted/60 [animation-delay:-0.3s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted/60 [animation-delay:-0.15s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted/60" />
          </span>
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-2.5 animate-rise">
      <Avatar />
      <div className="rounded-2xl rounded-bl-md bg-white/70 px-4 py-3 ring-1 ring-black/5 backdrop-blur">
        <span className="text-sm font-medium shimmer-text">{current}</span>
        {steps.length > 1 && (
          <ol className="mt-2 space-y-0.5">
            {steps.slice(0, -1).map((s, i) => (
              <li key={i} className="text-xs text-muted/70">
                {s}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

export default function ChatPanel({
  username,
  messages,
  liveSteps,
  busy,
  thinking,
  disabled,
  disabledReason,
  onSend,
}: {
  username: string;
  messages: ChatMessage[];
  liveSteps: string[];
  busy: boolean;
  thinking: boolean;
  disabled: boolean;
  disabledReason?: string;
  onSend: (text: string) => void;
}) {
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, liveSteps, thinking]);

  function submit() {
    const t = input.trim();
    if (!t || busy || disabled) return;
    onSend(t);
    setInput("");
  }

  const empty = messages.length === 0 && !busy;

  return (
    <section className="flex h-full flex-col">
      {/* Header — transparent, content aligned to the centered column */}
      <header className="shrink-0 px-4 py-4">
        <div className="mx-auto flex w-full max-w-3xl items-center gap-3">
          <div className="relative">
            <Avatar />
            <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-approve" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-ink">{ASSISTANT_NAME}</h2>
            <p className="text-xs text-muted">Online · ready to help</p>
          </div>
        </div>
      </header>

      {/* Scroll region spans the FULL pane width, so the scrollbar sits at the
          pane's right edge — and only appears when content overflows. Message
          content is centered inside via max-w-3xl. */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col px-4 py-4">
          {empty && !disabled && (
            <div className="flex flex-1 flex-col items-center justify-center text-center">
              <h3 className="bg-gradient-to-r from-ink to-[#4b5563] bg-clip-text text-3xl font-semibold text-transparent">
                Hello, {username}
              </h3>
              <p className="mt-2 text-sm text-muted">How can I help you today?</p>
            </div>
          )}

          {disabled && (
            <div className="mx-auto mt-10 max-w-sm rounded-2xl bg-white/70 p-5 text-center text-sm text-muted ring-1 ring-black/5 backdrop-blur">
              {disabledReason || "Chat is disabled for this account."}
            </div>
          )}

          {!empty && !disabled && (
            <div className="space-y-4">
              {messages.map((m, i) => {
                if (m.kind === "user") {
                  return (
                    <div key={i} className="flex justify-end animate-rise">
                      <div className="max-w-[78%] rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-sm leading-relaxed text-white shadow-sm">
                        {m.text}
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={i} className="flex items-start gap-2.5 animate-rise">
                    <Avatar />
                    <div className="max-w-[82%] rounded-2xl rounded-bl-md bg-white/70 px-4 py-3 text-sm leading-relaxed text-ink ring-1 ring-black/5 backdrop-blur">
                      {m.steps && m.steps.length > 0 && (
                        <Reasoning steps={m.steps} />
                      )}
                      {m.decision && (
                        <div className="mb-2">
                          <DecisionBadge decision={m.decision} />
                        </div>
                      )}
                      <p className="whitespace-pre-wrap">{m.text}</p>
                    </div>
                  </div>
                );
              })}
              {thinking && <Thinking steps={liveSteps} />}
            </div>
          )}

          <div ref={endRef} />
        </div>
      </div>

      {/* Composer — floating, translucent, centered */}
      <div className="shrink-0 px-4 pb-5 pt-2">
        <div className="mx-auto flex max-w-2xl items-end gap-2 rounded-full border border-black/10 bg-white/80 p-1.5 pl-4 shadow-lg shadow-black/[0.04] backdrop-blur focus-within:border-ink/40">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={1}
            disabled={disabled}
            placeholder={
              disabled ? "Chat disabled for this account" : `Message ${ASSISTANT_NAME}…`
            }
            className="max-h-32 flex-1 resize-none bg-transparent py-2 text-sm outline-none disabled:cursor-not-allowed"
          />
          <button
            onClick={submit}
            disabled={busy || disabled || !input.trim()}
            aria-label="Send"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink text-white transition hover:opacity-90 disabled:opacity-30"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>
    </section>
  );
}
