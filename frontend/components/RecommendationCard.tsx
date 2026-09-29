"use client";

import { AlertTriangle, GraduationCap, Lightbulb, ShieldCheck, Target } from "lucide-react";
import type { Diagnosis } from "@/lib/types";
import EvidencePanel from "./EvidencePanel";

function confidenceLabel(c: number) {
  if (c >= 0.8) return { label: "High", cls: "text-ok", bar: "bg-ok" };
  if (c >= 0.5) return { label: "Medium", cls: "text-warn", bar: "bg-warn" };
  return { label: "Low", cls: "text-crit", bar: "bg-crit" };
}

export default function RecommendationCard({ d }: { d: Diagnosis }) {
  const conf = confidenceLabel(d.confidence);
  return (
    <section className="panel fade-in overflow-hidden">
      <div className="grid gap-px bg-line md:grid-cols-[1fr_190px]">
        <div className="bg-panel p-4">
          <div className="label flex items-center gap-1.5"><Target className="h-3 w-3 text-crit" /> Root cause</div>
          <div className="mt-1.5 text-[20px] font-semibold leading-tight">{d.root_cause}</div>
          <p className="mt-2 text-[12.5px] leading-relaxed text-muted">{d.summary}</p>
        </div>
        <div className="bg-panel p-4">
          <div className="label">Confidence</div>
          <div className={`mt-1.5 text-[22px] font-semibold ${conf.cls}`}>{conf.label}</div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-panel-2">
            <div className={`h-full ${conf.bar}`} style={{ width: `${Math.round(d.confidence * 100)}%` }} />
          </div>
          <div className="mono mt-1 text-[10px] text-dim">model-reported {d.confidence.toFixed(2)}</div>
        </div>
      </div>

      <div className="space-y-4 p-4">
        <EvidencePanel d={d} />

        {d.learned_patterns.length > 0 && (
          <div>
            <div className="label mb-2 flex items-center gap-1.5"><Lightbulb className="h-3 w-3 text-mem" /> Learned patterns applied</div>
            <ul className="space-y-1.5">
              {d.learned_patterns.map((p, i) => (
                <li key={i} className={`rounded-md border p-2.5 text-[12.5px] leading-snug ${p.from_engineer_feedback ? "border-mem/60 bg-mem/[.08]" : "border-line bg-panel-2"}`}>
                  {p.from_engineer_feedback && (
                    <span className="mono mr-2 inline-flex items-center gap-1 rounded bg-mem px-1.5 py-px text-[9.5px] font-bold text-bg">
                      <GraduationCap className="h-3 w-3" /> TAUGHT BY ENGINEER
                    </span>
                  )}
                  {p.pattern}
                  <span className="mono ml-1.5 text-[10.5px] text-dim">— {p.source}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <div className="label mb-2 flex items-center gap-1.5"><ShieldCheck className="h-3 w-3 text-ok" /> Recommended actions</div>
          <ol className="space-y-2">
            {d.recommended_actions.map((a, i) => (
              <li key={i} className="flex gap-3">
                <span className="mono grid h-5 w-5 shrink-0 place-items-center rounded bg-ok/15 text-[11px] font-bold text-ok">{i + 1}</span>
                <div className="leading-snug">
                  <div className="text-[13px] font-medium">{a.action}</div>
                  <div className="text-[11.5px] text-muted">{a.rationale}</div>
                </div>
              </li>
            ))}
          </ol>
          <div className="mono mt-2 text-[10px] text-dim">Recommendations only — OpsMind never modifies infrastructure.</div>
        </div>

        {d.warnings.length > 0 && (
          <div className="rounded-md border border-warn/35 bg-warn/[.06] p-3">
            <div className="label mb-1.5 flex items-center gap-1.5 !text-warn"><AlertTriangle className="h-3 w-3" /> Warnings</div>
            <ul className="space-y-1">
              {d.warnings.map((w, i) => <li key={i} className="text-[12.5px] leading-snug text-warn/95">{w}</li>)}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
