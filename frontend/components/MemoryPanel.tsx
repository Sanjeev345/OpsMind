"use client";

import { useMemo, useState } from "react";
import { BrainCircuit, CloudOff, GraduationCap, Search } from "lucide-react";
import type { MemoryItem } from "@/lib/types";

type Kind = "taught" | "failed_approach" | "incident_experience" | "learned_pattern" | "engineer_decision" | "observation" | "other";

export function memoryKind(m: MemoryItem): Kind {
  if (m.source === "engineer_feedback") return "taught";
  if (m.memory_type === "failed_approach") return "failed_approach";
  if (m.memory_type === "incident_experience") return "incident_experience";
  if (m.memory_type === "learned_pattern") return "learned_pattern";
  if (m.memory_type === "engineer_decision") return "engineer_decision";
  if (m.fact_type === "observation") return "observation";
  return "other";
}

const KIND: Record<Kind, { label: string; cls: string; hint: string }> = {
  taught: { label: "Taught by engineer", cls: "border-mem/60 bg-mem/15 text-mem", hint: "Retained from engineer feedback in OpsMind" },
  failed_approach: { label: "Failed approach", cls: "border-crit/40 bg-crit/10 text-crit", hint: "A remediation that did not work" },
  incident_experience: { label: "Incident experience", cls: "border-info/40 bg-info/10 text-info", hint: "Fact extracted from a past incident" },
  learned_pattern: { label: "Learned pattern", cls: "border-mem/40 bg-mem/10 text-mem", hint: "Cross-incident postmortem knowledge" },
  engineer_decision: { label: "Engineer decision", cls: "border-warn/40 bg-warn/10 text-warn", hint: "A past engineering decision" },
  observation: { label: "Hindsight observation", cls: "border-ok/40 bg-ok/10 text-ok", hint: "Consolidated automatically by Hindsight across memories" },
  other: { label: "Memory", cls: "border-line-2 bg-panel-2 text-muted", hint: "" },
};

export default function MemoryPanel({
  memories, queries, status, error, running, bankId, highlightDocIds,
}: {
  memories: MemoryItem[]; queries: string[]; status: "idle" | "ok" | "unavailable" | "not_used"; error?: string | null;
  running: boolean; bankId?: string; highlightDocIds: string[];
}) {
  const [filter, setFilter] = useState<Kind | "all">("all");
  const sorted = useMemo(() => {
    const hl = new Set(highlightDocIds);
    return [...memories].sort((a, b) => {
      const ah = a.document_id && hl.has(a.document_id) ? 1 : 0;
      const bh = b.document_id && hl.has(b.document_id) ? 1 : 0;
      if (ah !== bh) return bh - ah;
      return (b.score ?? -1) - (a.score ?? -1);
    });
  }, [memories, highlightDocIds]);

  const counts = useMemo(() => {
    const c: Partial<Record<Kind, number>> = {};
    for (const m of memories) c[memoryKind(m)] = (c[memoryKind(m)] ?? 0) + 1;
    return c;
  }, [memories]);

  // Incidents referenced by recalled memories (from metadata or literal INC-### mentions in the memory text).
  const referenced = useMemo(() => {
    const c = new Map<string, number>();
    for (const m of memories) for (const id of m.mentioned_incidents ?? []) c.set(id, (c.get(id) ?? 0) + 1);
    return [...c.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
  }, [memories]);

  const shown = filter === "all" ? sorted : sorted.filter((m) => memoryKind(m) === filter);

  return (
    <section className="panel flex min-h-[420px] flex-col overflow-hidden border-mem/25 shadow-[0_0_0_1px_rgba(167,139,250,.06),0_0_40px_-18px_rgba(139,92,246,.45)]">
      <div className="border-b border-line bg-mem/[.04] px-4 py-3">
        <div className="flex items-center gap-2">
          <BrainCircuit className="h-4 w-4 text-mem" />
          <span className="mono text-[12px] font-bold tracking-[.2em] text-mem">HINDSIGHT MEMORY</span>
          <span className="mono ml-auto text-[10.5px] text-dim">bank: {bankId ?? "opsmind"}</span>
        </div>
        <div className="mt-1 text-[11.5px] text-muted">
          {status === "idle" && !running && "Long-term organizational memory. Recalled live during each investigation."}
          {running && memories.length === 0 && "Waiting for the agent to query memory…"}
          {memories.length > 0 && `${memories.length} memories recalled via ${queries.length} recall ${queries.length === 1 ? "query" : "queries"}`}
        </div>
      </div>

      {status === "unavailable" && (
        <div className="m-3 flex gap-3 rounded-md border border-warn/40 bg-warn/[.07] p-3">
          <CloudOff className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          <div className="text-[12px] leading-relaxed text-warn">
            <div className="font-semibold">Hindsight unavailable</div>
            Historical memory could not be retrieved. Current incident analysis can continue, but historical learning is temporarily unavailable.
            {error && <div className="mono mt-1 text-[10.5px] opacity-80">{error}</div>}
          </div>
        </div>
      )}

      {queries.length > 0 && (
        <div className="space-y-1 border-b border-line px-4 py-2.5">
          {queries.map((q, i) => (
            <div key={i} className="flex items-start gap-2 text-[11px] text-muted">
              <Search className="mt-0.5 h-3 w-3 shrink-0 text-mem" />
              <span className="mono leading-snug">recall(“{q}”)</span>
            </div>
          ))}
        </div>
      )}

      {referenced.length > 0 && (
        <div className="border-b border-line px-4 py-2.5">
          <div className="label mb-1.5 !text-[9.5px]">Incidents referenced by recalled memories</div>
          <div className="flex flex-wrap gap-1.5">
            {referenced.map(([id, n]) => (
              <span key={id} className="mono rounded border border-line-2 bg-panel-2 px-1.5 py-0.5 text-[11px]">
                {id} <span className="text-dim">×{n}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {memories.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-b border-line px-4 py-2">
          <button onClick={() => setFilter("all")} className={`rounded px-2 py-0.5 text-[10.5px] ${filter === "all" ? "bg-text text-bg" : "text-muted hover:text-text"}`}>
            All {memories.length}
          </button>
          {(Object.keys(KIND) as Kind[]).filter((k) => counts[k]).map((k) => (
            <button key={k} onClick={() => setFilter(k)} title={KIND[k].hint}
              className={`rounded border px-2 py-0.5 text-[10.5px] ${filter === k ? KIND[k].cls : "border-transparent text-muted hover:text-text"}`}>
              {KIND[k].label} {counts[k]}
            </button>
          ))}
        </div>
      )}

      <div className="scroll-thin flex-1 space-y-2 overflow-y-auto p-3 xl:max-h-[calc(100vh-330px)]">
        {memories.length === 0 && !running && status !== "unavailable" && (
          <div className="px-2 py-8 text-center text-[12px] leading-relaxed text-dim">
            Nothing recalled yet.<br />Investigate an incident to see what OpsMind remembers.
          </div>
        )}
        {running && memories.length === 0 && (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => <div key={i} className="h-16 animate-pulse rounded-md bg-panel-2" />)}
          </div>
        )}
        {shown.map((m, idx) => {
          const k = memoryKind(m);
          const isNew = !!m.document_id && highlightDocIds.includes(m.document_id);
          return (
            <article
              key={m.id}
              className={`fade-in rounded-md border p-3 ${
                isNew ? "learned-glow border-mem bg-mem/[.09]" : k === "failed_approach" ? "border-crit/25 bg-crit/[.03]" : "border-line bg-panel-2"
              }`}
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mono text-[10px] text-dim">#{idx + 1}</span>
                <span title={KIND[k].hint} className={`mono rounded border px-1.5 py-px text-[9.5px] font-semibold uppercase tracking-wider ${KIND[k].cls}`}>
                  {k === "taught" && <GraduationCap className="-mt-px mr-1 inline h-3 w-3" />}
                  {KIND[k].label}
                </span>
                {isNew && <span className="mono rounded bg-mem px-1.5 py-px text-[9.5px] font-bold text-bg">NEW · LEARNED THIS SESSION</span>}
                {m.incident_id && <span className="mono text-[11px] font-semibold">{m.incident_id}</span>}
                {m.score != null && (
                  <span className="mono ml-auto text-[10px] text-dim" title="Hindsight's final recall ranking score (as returned by the API)">
                    score {m.score.toFixed(2)}
                  </span>
                )}
              </div>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-text/90">{m.text.replace(/\s*\|\s*When:[^|]*/g, "").trim()}</p>
              {(m.occurred_at || m.document_id) && (
                <div className="mono mt-1.5 flex flex-wrap gap-x-3 text-[10px] text-dim">
                  {m.occurred_at && <span>{m.occurred_at.slice(0, 10)}</span>}
                  {m.document_id && <span>doc: {m.document_id}</span>}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
