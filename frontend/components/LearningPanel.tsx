"use client";

import { Check, CheckCircle2, GraduationCap, Loader2, X } from "lucide-react";
import type { FeedbackForm, FeedbackResult } from "@/lib/types";

export default function LearningPanel({
  incidentId, form, setForm, onSubmit, submitting, result, error, onChoose,
}: {
  incidentId: string; form: FeedbackForm; setForm: (f: FeedbackForm) => void; onSubmit: () => void;
  submitting: boolean; result: FeedbackResult | null; error: string | null; onChoose: (correct: boolean) => void;
}) {
  if (result) {
    return (
      <section id="learning-panel" className="panel fade-in overflow-hidden border-ok/40">
        <div className="flex items-center gap-3 border-b border-ok/25 bg-ok/[.07] px-4 py-3">
          <CheckCircle2 className="h-5 w-5 text-ok" />
          <div>
            <div className="mono text-[13px] font-bold tracking-[.16em] text-ok">EXPERIENCE STORED</div>
            <div className="text-[12px] text-muted">Hindsight memory updated. OpsMind can use this experience in future investigations.</div>
          </div>
        </div>
        <div className="space-y-3 p-4">
          <div>
            <div className="label mb-1">Lesson retained</div>
            <p className="rounded-md border border-mem/40 bg-mem/[.07] p-3 text-[13px] leading-relaxed">{result.lesson}</p>
            <div className="mono mt-1 text-[10px] text-dim">
              {result.lesson_generated_by === "llm" ? "generalized by the LLM from your feedback" : "built from your feedback"}
            </div>
          </div>
          <div className="mono space-y-0.5 text-[10.5px] text-muted">
            {result.retained.map((r) => (
              <div key={r.document_id}>✓ retain → bank <span className="text-text">{result.bank_id}</span> · doc <span className="text-mem">{r.document_id}</span> · {r.memory_type}</div>
            ))}
            {result.memory_stats && <div>bank now holds {result.memory_stats.total_memories} memories</div>}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section id="learning-panel" className="panel fade-in overflow-hidden">
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <GraduationCap className="h-4 w-4 text-mem" />
        <span className="mono text-[12px] font-bold tracking-[.16em]">DID OPSMIND GET IT RIGHT?</span>
        <span className="mono ml-auto text-[10.5px] text-dim">{incidentId}</span>
      </div>
      <div className="space-y-3 p-4">
        <div className="grid grid-cols-2 gap-2">
          <button onClick={() => onChoose(true)}
            className={`flex items-center justify-center gap-2 rounded-md border py-2.5 text-[12.5px] font-semibold tracking-[.12em] transition ${
              form.correct === true ? "border-ok bg-ok/15 text-ok" : "border-line text-muted hover:border-ok/50 hover:text-ok"}`}>
            <Check className="h-4 w-4" /> CORRECT
          </button>
          <button onClick={() => onChoose(false)}
            className={`flex items-center justify-center gap-2 rounded-md border py-2.5 text-[12.5px] font-semibold tracking-[.12em] transition ${
              form.correct === false ? "border-crit bg-crit/15 text-crit" : "border-line text-muted hover:border-crit/50 hover:text-crit"}`}>
            <X className="h-4 w-4" /> INCORRECT
          </button>
        </div>

        {form.correct !== null && (
          <div className="fade-in space-y-2.5">
            {([
              ["actual_root_cause", "Actual root cause", 1],
              ["actual_resolution", "Actual resolution", 2],
              ["engineer_note", "Engineer note — what should OpsMind remember?", 2],
            ] as const).map(([key, label, rows]) => (
              <label key={key} className="block">
                <span className="label !text-[9.5px]">{label}</span>
                <textarea
                  rows={rows}
                  value={form[key]}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  className="mt-1 w-full resize-none rounded-md border border-line bg-bg px-3 py-2 text-[12.5px] leading-snug text-text outline-none transition focus:border-mem/60"
                />
              </label>
            ))}
            {error && <div className="rounded-md border border-crit/40 bg-crit/10 px-3 py-2 text-[12px] text-crit">{error}</div>}
            <button
              onClick={onSubmit}
              disabled={submitting}
              className="flex w-full items-center justify-center gap-2 rounded-md bg-mem-strong py-2.5 text-[12.5px] font-semibold tracking-[.14em] text-white transition hover:bg-mem disabled:opacity-50"
            >
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <GraduationCap className="h-4 w-4" />}
              {submitting ? "RETAINING IN HINDSIGHT…" : "TEACH OPSMIND"}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
