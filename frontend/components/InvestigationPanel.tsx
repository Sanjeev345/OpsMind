"use client";

import { GraduationCap, Loader2, OctagonAlert, Sparkles } from "lucide-react";
import type { MemoryItem, TraceEvent, InvestigationResult } from "@/lib/types";
import AgentActivity from "./AgentActivity";
import RecommendationCard from "./RecommendationCard";

export interface RunState {
  status: "running" | "done" | "error";
  trace: TraceEvent[];
  memories: MemoryItem[];
  queries: string[];
  result?: InvestigationResult;
  error?: string;
  startedAt: number;
}

export interface LearnedRecall {
  fromIncident: string;
  lesson: string;
  storedAt: string;
  memories: MemoryItem[];
}

export default function InvestigationPanel({ run, learned }: { run: RunState | undefined; learned: LearnedRecall | null }) {
  if (!run) {
    return (
      <section className="panel grid min-h-[260px] place-items-center p-8 text-center">
        <div>
          <Sparkles className="mx-auto h-6 w-6 text-dim" />
          <div className="mt-3 text-[14px] font-medium">No investigation yet</div>
          <div className="mt-1 max-w-sm text-[12.5px] leading-relaxed text-dim">
            Click <span className="mono text-text">INVESTIGATE</span> to have OpsMind analyse current telemetry and recall
            how this infrastructure failed before — or press <span className="mono text-mem">RUN DEMO</span> for the full learning loop.
          </div>
        </div>
      </section>
    );
  }
  const r = run.result;
  return (
    <div className="space-y-4">
      {learned && (
        <section className="learned-glow fade-in overflow-hidden rounded-[10px] border border-mem bg-gradient-to-r from-mem/[.16] to-mem/[.04]">
          <div className="flex items-start gap-3 p-4">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-mem text-bg"><GraduationCap className="h-5 w-5" /></div>
            <div className="min-w-0">
              <div className="mono text-[15px] font-bold tracking-[.22em] text-mem">OPSMIND LEARNED</div>
              <div className="mt-0.5 text-[12.5px] text-text/90">
                The lesson an engineer taught on <span className="mono font-semibold">{learned.fromIncident}</span> was recalled from Hindsight
                ({learned.memories.length} {learned.memories.length === 1 ? "memory" : "memories"}) and fed into this investigation.
              </div>
              <div className="mt-2 rounded-md border border-mem/30 bg-bg/50 p-2.5 text-[12px] italic leading-snug text-muted">“{learned.lesson}”</div>
              <div className="mono mt-1.5 text-[10px] text-dim">retained {new Date(learned.storedAt).toLocaleTimeString()} · recalled {r ? new Date(r.completed_at).toLocaleTimeString() : "now"}</div>
            </div>
          </div>
        </section>
      )}

      <AgentActivity trace={run.trace} running={run.status === "running"} toolCalls={r?.tool_calls} durationMs={r?.duration_ms} model={r?.model} />

      {run.status === "running" && !r && (
        <div className="panel flex items-center gap-3 p-4 text-[12.5px] text-muted">
          <Loader2 className="h-4 w-4 animate-spin text-info" /> OpsMind is investigating with live telemetry and Hindsight memory…
        </div>
      )}

      {run.status === "error" && (
        <div className="panel flex gap-3 border-crit/40 p-4">
          <OctagonAlert className="h-5 w-5 shrink-0 text-crit" />
          <div>
            <div className="text-[13px] font-semibold text-crit">Investigation failed</div>
            <div className="mt-0.5 text-[12.5px] text-muted">{run.error}</div>
          </div>
        </div>
      )}

      {r && !r.diagnosis && (
        <div className="panel flex gap-3 border-crit/40 p-4">
          <OctagonAlert className="h-5 w-5 shrink-0 text-crit" />
          <div>
            <div className="text-[13px] font-semibold text-crit">LLM unavailable — no diagnosis generated</div>
            <div className="mt-0.5 text-[12.5px] text-muted">{r.diagnosis_error} Historical memory retrieved from Hindsight is still shown on the right.</div>
          </div>
        </div>
      )}

      {r?.diagnosis && <RecommendationCard d={r.diagnosis} />}
    </div>
  );
}
