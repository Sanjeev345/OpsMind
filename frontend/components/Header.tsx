"use client";

import { useEffect, useRef, useState } from "react";
import { BrainCircuit, Loader2, Play, RotateCcw } from "lucide-react";
import type { Health, MemoryStats } from "@/lib/types";

function StatusPill({ label, ok, configured, error }: { label: string; ok: boolean; configured: boolean; error?: string }) {
  const color = ok ? "bg-ok" : configured ? "bg-crit" : "bg-warn";
  const text = ok ? "CONNECTED" : configured ? "UNAVAILABLE" : "NOT CONFIGURED";
  return (
    <div title={error ?? ""} className="flex items-center gap-2 rounded-md border border-line bg-panel px-2.5 py-1.5">
      <span className={`h-2 w-2 rounded-full ${color} ${ok ? "" : "pulse-dot"}`} />
      <span className="mono text-[10.5px] tracking-[.12em] text-muted">
        {label} <span className={ok ? "text-text" : "text-crit"}>{text}</span>
      </span>
    </div>
  );
}

function Counter({ label, value, accent }: { label: string; value: number | undefined; accent?: boolean }) {
  const [bump, setBump] = useState(false);
  const prev = useRef(value);
  useEffect(() => {
    if (prev.current !== undefined && value !== undefined && value !== prev.current) {
      setBump(true);
      const t = setTimeout(() => setBump(false), 600);
      prev.current = value;
      return () => clearTimeout(t);
    }
    prev.current = value;
  }, [value]);
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className={`mono text-[15px] font-semibold tabular-nums ${accent ? "text-mem" : "text-text"} ${bump ? "bump" : ""}`}>
        {value ?? "—"}
      </span>
      <span className="label !text-[9px] !text-dim">{label}</span>
    </div>
  );
}

export default function Header({
  health, stats, demoRunning, busy, onRunDemo, onReset,
}: {
  health: Health | null; stats: MemoryStats | null; demoRunning: boolean; busy: boolean;
  onRunDemo: () => void; onReset: () => void;
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-bg/90 backdrop-blur">
      <div className="mx-auto flex max-w-[1680px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-lg border border-mem/40 bg-mem/10">
            <BrainCircuit className="h-5 w-5 text-mem" />
          </div>
          <div>
            <div className="mono text-[15px] font-bold tracking-[.22em]">OPSMIND</div>
            <div className="text-[12px] text-muted">Organizational memory for production incidents</div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <StatusPill label="HINDSIGHT" ok={!!health?.hindsight.connected} configured={health?.hindsight.configured ?? true} error={health?.hindsight.error} />
          <StatusPill label="GROQ" ok={!!health?.groq.connected} configured={health?.groq.configured ?? true} error={health?.groq.error} />
        </div>

        <div className="ml-auto flex items-center gap-5">
          <div className="hidden items-center gap-5 border-r border-line pr-5 md:flex" title={`Live stats of Hindsight bank "${stats?.bank_id ?? "opsmind"}"`}>
            <Counter label="memories" value={stats?.total_memories} accent />
            <Counter label="observations" value={stats?.total_observations} />
            <Counter label="documents" value={stats?.total_documents} />
            <Counter label="lessons taught" value={stats?.engineer_lessons} accent />
          </div>
          <button
            onClick={onReset}
            disabled={busy}
            className="flex items-center gap-1.5 rounded-md border border-line px-3 py-2 text-[12px] text-muted transition hover:border-line-2 hover:text-text disabled:opacity-40"
            title="Clear demo state and delete lessons taught in this demo (seeded history is kept)"
          >
            <RotateCcw className="h-3.5 w-3.5" /> Reset
          </button>
          <button
            onClick={onRunDemo}
            disabled={busy}
            className="flex items-center gap-2 rounded-md bg-mem-strong px-4 py-2 text-[12px] font-semibold tracking-[.12em] text-white transition hover:bg-mem disabled:opacity-50"
          >
            {demoRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5 fill-white" />}
            {demoRunning ? "DEMO RUNNING" : "RUN DEMO"}
          </button>
        </div>
      </div>
    </header>
  );
}
