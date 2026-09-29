"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, streamInvestigation, ApiError } from "@/lib/api";
import type { FeedbackForm, FeedbackResult, Health, Incident, IncidentSummary, InvestigationResult, MemoryStats, TraceEvent } from "@/lib/types";
import Header from "./Header";
import LearningLoop, { type LoopStep } from "./LearningLoop";
import IncidentPanel, { IncidentQueue } from "./IncidentPanel";
import InvestigationPanel, { type LearnedRecall, type RunState } from "./InvestigationPanel";
import MemoryPanel from "./MemoryPanel";
import LearningPanel from "./LearningPanel";

const FIRST = "INC-027";
const SECOND = "INC-028";
const TAUGHT_KEY = "opsmind.taught.v1";

interface Taught {
  incidentId: string;
  docIds: string[];
  lesson: string;
  storedAt: string;
}

interface FeedbackState {
  form: FeedbackForm;
  submitting: boolean;
  result: FeedbackResult | null;
  error: string | null;
}

const EMPTY_FORM: FeedbackForm = { correct: null, actual_root_cause: "", actual_resolution: "", engineer_note: "" };

const DEMO_FEEDBACK: FeedbackForm = {
  correct: true,
  actual_root_cause: "Redis connection pool exhaustion in payment-api (application-side pool saturated after v2.8.4)",
  actual_resolution: "Increased the payment-api Redis connection pool from 100 to 150 and restarted API workers. Redis itself was not restarted.",
  engineer_note: "Do not restart Redis for this failure pattern. Redis server was healthy (CPU 29%, 0 evictions) — runbook RB-REDIS-01 step 2 (restart Redis) is outdated for this signature.",
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function upsertTrace(list: TraceEvent[], ev: TraceEvent) {
  const i = list.findIndex((e) => e.id === ev.id);
  if (i === -1) return [...list, ev];
  const next = list.slice();
  next[i] = ev;
  return next;
}

export default function Dashboard() {
  const [health, setHealth] = useState<Health | null>(null);
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [details, setDetails] = useState<Record<string, Incident>>({});
  const [selectedId, setSelectedId] = useState<string>(FIRST);
  const [runs, setRuns] = useState<Record<string, RunState>>({});
  const [feedback, setFeedback] = useState<Record<string, FeedbackState>>({});
  const [taught, setTaught] = useState<Taught | null>(null);
  const [demoRunning, setDemoRunning] = useState(false);
  const [bootError, setBootError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const runsRef = useRef(runs);
  runsRef.current = runs;

  // ------------------------------------------------------------------ data loading
  const refreshStats = useCallback(() => api.stats().then(setStats).catch(() => {}), []);
  const refreshIncidents = useCallback(() => api.incidents().then(setIncidents).catch((e: ApiError) => setBootError(e.message)), []);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(TAUGHT_KEY);
      if (raw) setTaught(JSON.parse(raw));
    } catch {}
    refreshIncidents();
    refreshStats();
    const loadHealth = () => api.health().then((h) => { setHealth(h); setBootError(null); }).catch((e: ApiError) => setBootError(e.message));
    loadHealth();
    const h = setInterval(loadHealth, 30000);
    const s = setInterval(refreshStats, 20000);
    return () => { clearInterval(h); clearInterval(s); };
  }, [refreshIncidents, refreshStats]);

  const loadIncident = useCallback(async (id: string) => {
    const inc = await api.incident(id);
    setDetails((d) => ({ ...d, [id]: inc }));
    return inc;
  }, []);

  useEffect(() => { if (selectedId && !details[selectedId]) loadIncident(selectedId).catch(() => {}); }, [selectedId, details, loadIncident]);

  const persistTaught = (t: Taught | null) => {
    setTaught(t);
    try { t ? localStorage.setItem(TAUGHT_KEY, JSON.stringify(t)) : localStorage.removeItem(TAUGHT_KEY); } catch {}
  };

  // ------------------------------------------------------------------ investigation
  const investigate = useCallback(async (id: string): Promise<InvestigationResult | null> => {
    setRuns((r) => ({ ...r, [id]: { status: "running", trace: [], memories: [], queries: [], startedAt: Date.now() } }));
    setFeedback((f) => ({ ...f, [id]: { form: EMPTY_FORM, submitting: false, result: null, error: null } }));
    const patch = (fn: (s: RunState) => RunState) => setRuns((r) => (r[id] ? { ...r, [id]: fn(r[id]) } : r));
    let final: InvestigationResult | null = null;
    try {
      await streamInvestigation(id, (e) => {
        if (e.type === "trace") patch((s) => ({ ...s, trace: upsertTrace(s.trace, e.event) }));
        else if (e.type === "memories") patch((s) => ({ ...s, memories: e.memories, queries: e.queries }));
        else if (e.type === "result") {
          final = e.result;
          patch((s) => ({ ...s, status: "done", result: e.result, trace: e.result.trace, memories: e.result.memories, queries: e.result.memory_queries }));
          setDetails((d) => ({ ...d, [id]: e.result.incident }));
        } else if (e.type === "error") patch((s) => ({ ...s, status: "error", error: e.message }));
      });
    } catch (err) {
      patch((s) => ({ ...s, status: "error", error: err instanceof Error ? err.message : "Investigation failed" }));
    }
    patch((s) => (s.status === "running" ? { ...s, status: "error", error: "Stream ended unexpectedly" } : s));
    refreshIncidents();
    refreshStats();
    return final;
  }, [refreshIncidents, refreshStats]);

  // ------------------------------------------------------------------ feedback
  const fb = feedback[selectedId] ?? { form: EMPTY_FORM, submitting: false, result: null, error: null };
  const setFb = (id: string, patch: Partial<FeedbackState>) =>
    setFeedback((f) => ({ ...f, [id]: { ...(f[id] ?? { form: EMPTY_FORM, submitting: false, result: null, error: null }), ...patch } }));

  const chooseVerdict = (correct: boolean) => {
    const d = runs[selectedId]?.result?.diagnosis;
    setFb(selectedId, {
      form: correct
        ? { correct, actual_root_cause: d?.root_cause ?? "", actual_resolution: d?.recommended_actions.slice(0, 2).map((a) => a.action).join(" ") ?? "", engineer_note: fb.form.engineer_note }
        : { correct, actual_root_cause: "", actual_resolution: "", engineer_note: fb.form.engineer_note },
    });
  };

  const submitFeedback = useCallback(async (id: string, form: FeedbackForm) => {
    setFb(id, { submitting: true, error: null, form });
    try {
      const res = await api.feedback(id, form);
      setFb(id, { submitting: false, result: res });
      persistTaught({ incidentId: id, docIds: res.retained.map((r) => r.document_id), lesson: res.lesson, storedAt: res.stored_at });
      if (res.memory_stats) setStats((s) => ({ ...(s as MemoryStats), ...res.memory_stats!, engineer_lessons: (s?.engineer_lessons ?? 0) + 1 }));
      refreshIncidents();
      setTimeout(refreshStats, 1500);
      return true;
    } catch (err) {
      setFb(id, { submitting: false, error: err instanceof Error ? err.message : "Failed to store feedback" });
      return false;
    }
  }, [refreshIncidents, refreshStats]);

  // ------------------------------------------------------------------ demo
  const runDemo = async () => {
    setDemoRunning(true);
    try {
      setSelectedId(FIRST);
      await sleep(400);
      const first = await investigate(FIRST);
      if (!first?.diagnosis) throw new Error("First investigation did not produce a diagnosis");
      await sleep(1800);
      setFb(FIRST, { form: DEMO_FEEDBACK });
      document.getElementById("learning-panel")?.scrollIntoView({ behavior: "smooth", block: "center" });
      await sleep(3200);
      if (!(await submitFeedback(FIRST, DEMO_FEEDBACK))) throw new Error("Feedback could not be stored");
      await sleep(3000);
      setSelectedId(SECOND);
      window.scrollTo({ top: 0, behavior: "smooth" });
      await sleep(900);
      await investigate(SECOND);
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Demo stopped");
      setTimeout(() => setToast(null), 5000);
    } finally {
      setDemoRunning(false);
    }
  };

  const reset = async () => {
    try {
      const r = await api.reset();
      setRuns({}); setFeedback({}); persistTaught(null); setDetails({}); setSelectedId(FIRST);
      setToast(`Demo reset · removed ${r.deleted_learned_memories} learned memories from Hindsight (seeded history kept)`);
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Reset failed");
    }
    setTimeout(() => setToast(null), 5000);
    refreshIncidents();
    refreshStats();
  };

  // ------------------------------------------------------------------ derived
  const run = runs[selectedId];
  const incident = details[selectedId] ?? null;
  const anyRunning = Object.values(runs).some((r) => r.status === "running");

  const learnedFor = (id: string): LearnedRecall | null => {
    const r = runs[id];
    if (!taught || !r || r.startedAt < new Date(taught.storedAt).getTime()) return null;
    const mems = r.memories.filter((m) => m.document_id && taught.docIds.includes(m.document_id));
    return mems.length ? { fromIncident: taught.incidentId, lesson: taught.lesson, storedAt: taught.storedAt, memories: mems } : null;
  };
  const learned = learnedFor(selectedId);

  const steps: LoopStep[] = useMemo(() => {
    const r1 = runs[FIRST], r2 = runs[SECOND];
    const second = r2 && taught && r2.startedAt >= new Date(taught.storedAt).getTime() ? r2 : undefined;
    const l2 = learnedFor(SECOND);
    const s = [
      { label: `Investigate ${FIRST}`, sub: "live telemetry + tools", done: r1?.status === "done" },
      { label: "Recall history", sub: "Hindsight recall", done: (r1?.memories.length ?? 0) > 0 },
      { label: "Engineer teaches", sub: "Hindsight retain", done: !!taught },
      { label: `Investigate ${SECOND}`, sub: "similar incident", done: second?.status === "done" },
      { label: "OpsMind learned", sub: "lesson recalled & applied", done: !!l2 },
    ];
    const firstOpen = s.findIndex((x) => !x.done);
    return s.map((x, i) => ({ ...x, active: i === firstOpen && (demoRunning || anyRunning || i > 0) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs, taught, demoRunning, anyRunning]);

  const memStatus = !run ? "idle" : run.result ? run.result.memory_status : run.memories.length ? "ok" : "idle";

  return (
    <div className="min-h-screen">
      <Header health={health} stats={stats} demoRunning={demoRunning} busy={demoRunning || anyRunning} onRunDemo={runDemo} onReset={reset} />

      <main className="mx-auto max-w-[1680px] space-y-4 px-4 py-4 sm:px-6">
        {bootError && (
          <div className="rounded-md border border-crit/40 bg-crit/10 px-4 py-2.5 text-[12.5px] text-crit">
            {bootError}. Start the backend: <span className="mono">cd backend && uvicorn main:app --port 8000</span>
          </div>
        )}
        {health && !health.groq.connected && (
          <div className="rounded-md border border-warn/40 bg-warn/[.07] px-4 py-2.5 text-[12.5px] text-warn">
            Groq unavailable — {health.groq.error ?? "GROQ_API_KEY not configured"}. Investigations will not produce a diagnosis until this is fixed.
          </div>
        )}

        <LearningLoop steps={steps} />

        <div className="grid gap-4 xl:grid-cols-12">
          <div className="space-y-4 xl:col-span-3">
            <IncidentQueue incidents={incidents} selectedId={selectedId} onSelect={setSelectedId} disabled={demoRunning} />
            <IncidentPanel incident={incident} running={run?.status === "running"} canInvestigate={!demoRunning && !anyRunning}
              onInvestigate={() => investigate(selectedId)} />
          </div>

          <div className="space-y-4 xl:col-span-5">
            <InvestigationPanel run={run} learned={learned} />
            {run?.result?.diagnosis && (
              <LearningPanel
                incidentId={selectedId}
                form={fb.form}
                setForm={(f) => setFb(selectedId, { form: f })}
                onChoose={chooseVerdict}
                onSubmit={() => submitFeedback(selectedId, fb.form)}
                submitting={fb.submitting}
                result={fb.result}
                error={fb.error}
              />
            )}
          </div>

          <div className="xl:sticky xl:top-[76px] xl:col-span-4 xl:self-start">
            <MemoryPanel
              memories={run?.memories ?? []}
              queries={run?.queries ?? []}
              status={memStatus}
              error={run?.result?.memory_error}
              running={run?.status === "running"}
              bankId={health?.bank_id}
              highlightDocIds={learned ? taught!.docIds : []}
            />
          </div>
        </div>
      </main>

      {toast && (
        <div className="fade-in fixed bottom-4 left-1/2 z-30 -translate-x-1/2 rounded-md border border-line-2 bg-panel-2 px-4 py-2.5 text-[12.5px] shadow-xl">
          {toast}
        </div>
      )}
    </div>
  );
}
