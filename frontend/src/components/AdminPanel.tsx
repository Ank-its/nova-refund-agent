"use client";

import { useEffect, useState } from "react";
import { fetchTelemetry, type TelemetryPayload } from "@/lib/api";
import type { TraceEvent } from "@/lib/types";

// Right panel: live LangGraph execution trace + DB ops + latency + security
// alerts. Rendered only for admin / superuser roles.
export default function AdminPanel({
  token,
  liveTrace,
  refreshKey,
}: {
  token: string;
  liveTrace: TraceEvent[];
  refreshKey: number;
}) {
  const [telemetry, setTelemetry] = useState<TelemetryPayload | null>(null);

  useEffect(() => {
    let active = true;
    fetchTelemetry(token)
      .then((t) => active && setTelemetry(t))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [token, refreshKey]);

  return (
    <aside className="flex h-full flex-col border-l border-line bg-soft">
      <header className="border-b border-line px-5 py-4">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-approve" />
          <h2 className="text-sm font-semibold text-ink">Admin Telemetry</h2>
        </div>
        <p className="mt-0.5 text-xs text-muted">
          Live agent execution &amp; security monitoring
        </p>
      </header>

      <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
        <div className="grid grid-cols-3 gap-2">
          <Metric label="Tool calls" value={telemetry?.totals.tool_calls ?? "—"} />
          <Metric
            label="Avg latency"
            value={telemetry ? `${telemetry.totals.avg_latency_ms}ms` : "—"}
          />
          <Metric
            label="Approved"
            value={telemetry?.totals.refunds_by_status.approved ?? 0}
          />
        </div>

        <Section title="LangGraph execution (live)">
          {liveTrace.length === 0 && (
            <p className="text-xs text-muted">
              Run a chat request to see the execution trace.
            </p>
          )}
          <div className="space-y-1.5">
            {liveTrace.map((t, i) => (
              <TraceRow key={i} ev={t} />
            ))}
          </div>
        </Section>

        <Section title="Recent tool calls (audit log)">
          {!telemetry?.recent_calls.length && (
            <p className="text-xs text-muted">No tool calls yet.</p>
          )}
          <div className="space-y-1.5">
            {telemetry?.recent_calls.slice(0, 12).map((c) => {
              const decision = String(c.result.decision ?? "");
              return (
                <div
                  key={c.id}
                  className="rounded-xl border border-line bg-white px-3 py-2 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-ink">{c.tool}</span>
                    <span className="text-muted">{c.latency_ms}ms</span>
                  </div>
                  <div className="mt-0.5 text-muted">
                    {String(c.arguments.order_ref ?? "")} · {decision || "—"}
                  </div>
                </div>
              );
            })}
          </div>
        </Section>
      </div>
    </aside>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-line bg-white px-3 py-3">
      <div className="text-lg font-semibold text-ink">{value}</div>
      <div className="mt-0.5 text-[10px] uppercase tracking-wide text-muted">
        {label}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
        {title}
      </h3>
      {children}
    </div>
  );
}

function TraceRow({ ev }: { ev: TraceEvent }) {
  if (ev.kind === "security_alert") {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-reject">
        <div className="font-semibold">🚨 Security alert</div>
        <div className="mt-0.5">{ev.detail}</div>
        <div className="mt-1 truncate font-mono text-[10px] opacity-70">
          {ev.sample}
        </div>
      </div>
    );
  }
  if (ev.kind === "summary") {
    return (
      <div className="rounded-xl border border-line bg-white px-3 py-2 text-xs">
        <span className="font-semibold text-ink">Summary</span>{" "}
        <span className="text-muted">
          {ev.total_ms}ms · {ev.decision ?? "—"} · {ev.rule ?? "—"} ·{" "}
          {ev.used_llm ? "LLM" : "regex"}
        </span>
      </div>
    );
  }
  if (ev.kind === "error") {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-reject">
        error: {ev.detail}
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-line bg-white px-3 py-2 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-medium text-ink">{ev.label}</span>
        <span className="text-muted">{ev.elapsed_ms}ms</span>
      </div>
      <div className="mt-0.5 font-mono text-[10px] text-muted">
        [{ev.node}] {ev.detail}
      </div>
    </div>
  );
}
