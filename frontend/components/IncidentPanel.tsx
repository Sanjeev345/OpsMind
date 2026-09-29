"use client";

import { AlertTriangle, Archive, GitCommitHorizontal, Loader2, Search, Server } from "lucide-react";
import type { Incident, IncidentSummary } from "@/lib/types";

export function SeverityBadge({ severity }: { severity: string }) {
  const cls =
    severity === "SEV-1" ? "border-crit/50 bg-crit/15 text-crit"
      : severity === "SEV-2" ? "border-warn/50 bg-warn/10 text-warn"
      : "border-line-2 bg-panel-2 text-muted";
  return <span className={`mono rounded border px-1.5 py-0.5 text-[10px] font-semibold ${cls}`}>{severity}</span>;
}

const STATUS_STYLE: Record<string, string> = {
  open: "text-crit",
  investigating: "text-info",
  diagnosed: "text-warn",
  resolved: "text-ok",
};

export function IncidentQueue({
  incidents, selectedId, onSelect, disabled,
}: { incidents: IncidentSummary[]; selectedId: string | null; onSelect: (id: string) => void; disabled: boolean }) {
  const active = incidents.filter((i) => i.kind === "active");
  const historical = incidents.filter((i) => i.kind === "historical");
  return (
    <section className="panel">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <span className="label">Active incidents</span>
        <span className="mono text-[10.5px] text-crit">{active.filter((i) => i.status !== "resolved").length} OPEN</span>
      </div>
      <ul>
        {active.map((i) => {
          const sel = i.id === selectedId;
          return (
            <li key={i.id}>
              <button
                disabled={disabled}
                onClick={() => onSelect(i.id)}
                className={`flex w-full items-start gap-3 border-b border-line px-4 py-3 text-left transition last:border-b-0 disabled:cursor-not-allowed ${
                  sel ? "bg-panel-2 shadow-[inset_2px_0_0_var(--crit)]" : "hover:bg-panel-2/60"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="mono text-[13px] font-semibold">{i.id}</span>
                    <SeverityBadge severity={i.severity} />
                    <span className={`mono ml-auto text-[10px] uppercase tracking-wider ${STATUS_STYLE[i.status] ?? "text-muted"}`}>{i.status}</span>
                  </div>
                  <div className="mono mt-1 text-[11.5px] text-info">{i.service}</div>
                  <div className="mt-0.5 truncate text-[12px] text-muted">{i.title}</div>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
      <div className="flex items-center gap-2 border-t border-line px-4 py-2.5 text-[11.5px] text-dim">
        <Archive className="h-3.5 w-3.5" />
        {historical.length} resolved incidents in history · seeded into Hindsight
      </div>
    </section>
  );
}

function kv(obj: unknown): [string, string][] {
  if (!obj || typeof obj !== "object") return [];
  return Object.entries(obj as Record<string, string>).map(([k, v]) => [k.replace(/_/g, " "), String(v)]);
}

export default function IncidentPanel({
  incident, onInvestigate, running, canInvestigate,
}: { incident: Incident | null; onInvestigate: () => void; running: boolean; canInvestigate: boolean }) {
  if (!incident) {
    return <section className="panel p-6 text-[13px] text-dim">Select an incident.</section>;
  }
  const dep = incident.deployments[0];
  const redisServer = incident.health?.redis_server;
  const dbServer = incident.health?.postgres;
  const serverHealth = redisServer ? ["Redis server", redisServer] : dbServer ? ["Postgres", dbServer] : null;
  const oncall = typeof incident.health?.oncall_note === "string" ? (incident.health.oncall_note as string) : null;

  return (
    <section className="panel overflow-hidden">
      <div className="border-b border-line px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="label">Current incident</span>
          <span className="ml-auto mono text-[10.5px] text-dim">{new Date(incident.timestamp).toUTCString().slice(17, 22)} UTC</span>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <span className="mono text-[18px] font-bold">{incident.id}</span>
          <SeverityBadge severity={incident.severity} />
          <span className="mono rounded border border-info/30 bg-info/10 px-1.5 py-0.5 text-[10.5px] text-info">{incident.service}</span>
        </div>
        <div className="mt-1.5 text-[13px] leading-snug text-text">{incident.title}</div>
        <div className="mt-1 text-[12px] leading-snug text-muted">{incident.summary}</div>
      </div>

      <div className="grid grid-cols-2 gap-px bg-line">
        {incident.metrics.map((m) => (
          <div key={m.key} className="bg-panel px-4 py-3">
            <div className="label !text-[9.5px]">{m.label}</div>
            <div className={`mono mt-1 text-[20px] font-semibold tabular-nums ${m.status === "critical" ? "text-crit" : m.status === "warning" ? "text-warn" : "text-ok"}`}>
              {m.value}
            </div>
            {m.baseline && <div className="mono text-[10.5px] text-dim">baseline {m.baseline}</div>}
          </div>
        ))}
      </div>

      <div className="space-y-3 px-4 py-3">
        {dep && (
          <div className="rounded-md border border-line bg-panel-2 p-3">
            <div className="flex items-center gap-2 text-[11px] text-muted">
              <GitCommitHorizontal className="h-3.5 w-3.5" /> Latest deployment
              <span className="mono ml-auto text-warn">{dep.deployed_minutes_ago}m ago</span>
            </div>
            <div className="mono mt-1 text-[14px] font-semibold">{dep.version}</div>
            <div className="mt-0.5 text-[12px] leading-snug text-muted">{dep.change}</div>
          </div>
        )}
        {serverHealth && (
          <div className="rounded-md border border-line bg-panel-2 p-3">
            <div className="flex items-center gap-2 text-[11px] text-muted">
              <Server className="h-3.5 w-3.5" /> {serverHealth[0] as string} health
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {kv(serverHealth[1]).slice(0, 5).map(([k, v]) => (
                <span key={k} className="mono rounded bg-bg px-1.5 py-0.5 text-[10.5px] text-muted">
                  {k} <span className="text-text">{v}</span>
                </span>
              ))}
            </div>
          </div>
        )}
        {oncall && (
          <div className="flex gap-2 rounded-md border border-warn/30 bg-warn/[.06] p-2.5 text-[12px] text-warn">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {oncall}
          </div>
        )}
        <div className="space-y-1">
          {incident.alerts.map((a) => (
            <div key={a} className="flex items-center gap-2 text-[11.5px] text-muted">
              <span className="h-1.5 w-1.5 rounded-full bg-crit" /> {a}
            </div>
          ))}
        </div>
        <button
          onClick={onInvestigate}
          disabled={!canInvestigate || running}
          className="flex w-full items-center justify-center gap-2 rounded-md bg-text py-2.5 text-[12.5px] font-semibold tracking-[.14em] text-bg transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          {running ? "INVESTIGATING…" : "INVESTIGATE"}
        </button>
      </div>
    </section>
  );
}
