"use client";

import { useEffect, useRef } from "react";
import { AlertTriangle, BrainCircuit, CheckCircle2, Database, GitCommitHorizontal, Loader2, Search, Sparkles, XCircle } from "lucide-react";
import type { TraceEvent } from "@/lib/types";

function iconFor(ev: TraceEvent) {
  if (ev.status === "running") return <Loader2 className="h-3.5 w-3.5 animate-spin text-info" />;
  if (ev.status === "failed") return <XCircle className="h-3.5 w-3.5 text-crit" />;
  if (ev.status === "warning") return <AlertTriangle className="h-3.5 w-3.5 text-warn" />;
  if (ev.tool === "search_historical_incidents" || ev.step.startsWith("Found") || ev.step.includes("engineer")) return <BrainCircuit className="h-3.5 w-3.5 text-mem" />;
  return <CheckCircle2 className="h-3.5 w-3.5 text-ok" />;
}

function toolIcon(tool?: string | null) {
  if (tool === "search_historical_incidents") return <Database className="h-3 w-3" />;
  if (tool === "get_recent_deployments") return <GitCommitHorizontal className="h-3 w-3" />;
  if (tool) return <Search className="h-3 w-3" />;
  return <Sparkles className="h-3 w-3" />;
}

export default function AgentActivity({
  trace, running, toolCalls, durationMs, model,
}: { trace: TraceEvent[]; running: boolean; toolCalls?: number; durationMs?: number; model?: string }) {
  // Planning steps are noisy for the audience; show them dimmed. Follow the live tail while running.
  const listRef = useRef<HTMLOListElement>(null);
  useEffect(() => {
    const el = listRef.current;
    if (el && running) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [trace.length, running]);
  return (
    <section className="panel">
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="label">Agent activity</span>
        {running && <span className="mono flex items-center gap-1.5 text-[10.5px] text-info"><span className="h-1.5 w-1.5 rounded-full bg-info pulse-dot" /> LIVE</span>}
        <span className="mono ml-auto text-[10.5px] text-dim">
          {toolCalls !== undefined && `${toolCalls} tool calls · `}
          {durationMs !== undefined && `${(durationMs / 1000).toFixed(1)}s · `}
          {model}
        </span>
      </div>
      {trace.length === 0 ? (
        <div className="px-4 py-6 text-[12.5px] text-dim">
          The agent trace appears here in real time — every step is emitted by the backend as it happens.
        </div>
      ) : (
        <ol ref={listRef} className="scroll-thin max-h-[380px] overflow-y-auto px-2 py-2">
          {trace.map((ev) => {
            const planning = ev.step.startsWith("Planning");
            const memory = ev.tool === "search_historical_incidents" || ev.step.startsWith("Found") || ev.step.includes("engineer");
            return (
              <li
                key={ev.id}
                className={`fade-in flex items-start gap-2.5 rounded-md px-2 py-1.5 ${memory ? "bg-mem/[.06]" : ""} ${planning ? "opacity-55" : ""}`}
              >
                <span className="mt-[3px]">{iconFor(ev)}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className={`text-[12.5px] ${planning ? "text-muted" : "font-medium text-text"} ${memory ? "!text-mem" : ""}`}>{ev.step}</span>
                    {ev.tool && (
                      <span className="mono flex items-center gap-1 rounded bg-panel-2 px-1.5 py-px text-[9.5px] text-dim">
                        {toolIcon(ev.tool)} {ev.tool}
                      </span>
                    )}
                    {ev.duration_ms != null && ev.status !== "running" && (
                      <span className="mono ml-auto shrink-0 text-[10px] text-dim">{ev.duration_ms}ms</span>
                    )}
                  </div>
                  {ev.detail && <div className="mt-0.5 break-words text-[11.5px] leading-snug text-muted">{ev.detail}</div>}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
