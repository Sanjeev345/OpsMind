"use client";

import { Check } from "lucide-react";

export interface LoopStep {
  label: string;
  sub: string;
  done: boolean;
  active: boolean;
}

export default function LearningLoop({ steps }: { steps: LoopStep[] }) {
  return (
    <div className="panel flex flex-wrap items-stretch overflow-hidden">
      <div className="flex items-center border-r border-line px-4 py-2.5">
        <span className="label">Learning loop</span>
      </div>
      {steps.map((s, i) => (
        <div
          key={s.label}
          className={`relative flex min-w-[150px] flex-1 items-center gap-2.5 border-r border-line px-4 py-2.5 last:border-r-0 ${
            s.active ? "bg-mem/[.07]" : ""
          }`}
        >
          <span
            className={`grid h-5 w-5 shrink-0 place-items-center rounded-full border mono text-[10px] ${
              s.done ? "border-ok bg-ok/15 text-ok" : s.active ? "border-mem text-mem pulse-dot" : "border-line-2 text-dim"
            }`}
          >
            {s.done ? <Check className="h-3 w-3" /> : i + 1}
          </span>
          <div className="leading-tight">
            <div className={`text-[12px] font-medium ${s.done || s.active ? "text-text" : "text-dim"}`}>{s.label}</div>
            <div className="text-[11px] text-dim">{s.sub}</div>
          </div>
          {s.active && <span className="absolute inset-x-0 bottom-0 h-[2px] bg-mem" />}
        </div>
      ))}
    </div>
  );
}
