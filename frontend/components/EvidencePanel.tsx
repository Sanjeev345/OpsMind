"use client";

import { Activity, History, XOctagon } from "lucide-react";
import type { Diagnosis } from "@/lib/types";

/** Side-by-side: what OpsMind sees NOW vs. what it REMEMBERS. */
export default function EvidencePanel({ d }: { d: Diagnosis }) {
  const n = new Set(d.historical_matches.map((m) => m.incident_id)).size;
  return (
    <div className="grid gap-px overflow-hidden rounded-md border border-line bg-line md:grid-cols-2">
      <div className="bg-panel p-4">
        <div className="label mb-2 flex items-center gap-1.5"><Activity className="h-3 w-3 text-info" /> Current evidence</div>
        <ul className="space-y-1.5">
          {d.current_evidence.map((e, i) => (
            <li key={i} className="flex gap-2 text-[12.5px] leading-snug">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-info" /> {e}
            </li>
          ))}
        </ul>
      </div>
      <div className="bg-panel p-4">
        <div className="label mb-2 flex items-center gap-1.5"><History className="h-3 w-3 text-mem" /> Historical evidence · Hindsight</div>
        <div className="mb-2 text-[12.5px]">
          <span className="font-semibold text-mem">{n} previous {n === 1 ? "incident shows" : "incidents show"}</span> the same pattern.
        </div>
        <ul className="space-y-2">
          {d.historical_matches.map((m, i) => (
            <li key={i} className="text-[12px] leading-snug">
              <span className="mono mr-1.5 rounded bg-mem/10 px-1 py-px text-[11px] font-semibold text-mem">{m.incident_id}</span>
              <span className="text-muted">{m.reason}</span>
              <div className="mt-0.5 pl-1 text-[11.5px] text-ok/90">→ {m.outcome}</div>
            </li>
          ))}
        </ul>
        {d.failed_approaches.length > 0 && (
          <div className="mt-3 rounded-md border border-crit/30 bg-crit/[.06] p-2.5">
            <div className="label mb-1 flex items-center gap-1.5 !text-crit"><XOctagon className="h-3 w-3" /> Previously failed</div>
            {d.failed_approaches.map((f, i) => (
              <div key={i} className="text-[12px] leading-snug">
                <span className="mono mr-1 text-[11px] font-semibold">{f.incident_id}</span>
                <span className="font-medium">{f.action}</span> — <span className="text-muted">{f.result}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
