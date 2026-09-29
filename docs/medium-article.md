# OpsMind: Building an AI Incident Responder That Actually Learns From Its Mistakes

*How I used Hindsight memory, Groq and a human-in-the-loop feedback cycle to build an SRE agent that gets better with every outage.*

---

## The 3 a.m. problem

It's 3 a.m. Your pager goes off. `payment-api` is on fire: latency is up 25×, one in five checkout requests is failing, and Redis is throwing timeouts.

You open the runbook. Step 2 says: **"Restart the Redis cluster."**

What the runbook doesn't tell you is that eight months ago, someone on your team did exactly that during an almost identical incident — and it made things *worse*. The restart triggered a reconnect storm, error rates jumped to 34%, and the outage lasted 25 minutes longer. That lesson lives in a postmortem nobody reads, a Slack thread nobody can find, and the memory of an engineer who has since changed teams.

**Most production incidents are repeats. The knowledge to fix them already exists — it's just not available at the moment it's needed.**

That's the problem I set out to solve with **OpsMind**.

---

## What is OpsMind?

OpsMind is an AI incident-response agent that:

1. **Investigates** a live incident using current telemetry, deployments and runbooks
2. **Remembers** how your infrastructure failed before — root causes, fixes, and crucially, *fixes that didn't work*
3. **Recommends** a diagnosis that clearly separates what it sees *now* from what it *remembers*
4. **Learns** when an engineer confirms or corrects it
5. **Applies** that lesson the next time something similar happens

It's not a chatbot. It's a single-purpose SRE copilot built around one idea:

> **Persistent operational memory + agent reasoning + human feedback = better incident response over time.**

[📷 Screenshot: full OpsMind dashboard]

---

## The core idea: a learning loop

```
Incident
   ↓
Investigate current evidence
   ↓
Recall organizational memory (Hindsight)
   ↓
Diagnosis + recommendation
   ↓
Engineer feedback
   ↓
Retain the lesson (Hindsight)
   ↓
Future investigations improve
```

Most "AI for ops" demos stop at step 4. The interesting part is steps 5–7: the loop closes, and the system genuinely knows more after every incident than it did before.

---

## Why Hindsight?

The memory layer is **Hindsight**, and it's the heart of the project. I deliberately used *no* vector database, *no* local cache of answers, and *no* knowledge baked into the prompt. If OpsMind knows something about the past, it's because it recalled it from Hindsight at that moment.

A few Hindsight capabilities turned out to matter a lot:

- **Fact extraction on retain.** I store incident reports as documents; Hindsight breaks them into individual facts. 39 seeded documents became roughly 200 searchable memories.
- **Multi-strategy recall.** Semantic, keyword, graph and temporal retrieval run together, so a query like *"payment-api Redis timeouts pool full"* finds the right incidents even when wording differs.
- **Tag filtering.** Every memory is tagged by category (`failed_approach`, `engineer_decision`, `engineer_feedback`…). The agent runs a second, tag-filtered recall specifically for *what didn't work* and *what engineers taught us*.
- **Automatic observations.** Hindsight consolidates patterns on its own. Without being asked, it produced observations like *"payment-api experiences a recurring pattern of Redis connection pool exhaustion…"*
- **Stable document IDs.** Re-seeding replaces documents instead of duplicating them, which keeps the demo repeatable.

---

## The memory model

I organised OpsMind's memory into four categories — the kinds of knowledge a real SRE team accumulates:

- **Incident experience** — *"INC-003 affected payment-api. Root cause: Redis connection pool exhaustion. Resolution: increase the pool and restart API workers. Restarting Redis was not required."*
- **Failed approaches** — *"During INC-011, restarting Redis did not resolve the incident; the outage extended by 25 minutes."*
- **Engineer decisions** — *"Do not fail over Postgres when only the application pool is exhausted."*
- **Learned patterns** — *"When payment-api shows Redis timeouts with the client pool at capacity while the Redis server is healthy, investigate application-side pool exhaustion before restarting Redis."*

Each memory carries metadata — type, incident ID, service, root cause and source — so the UI can explain *where* a piece of knowledge came from.

I also seeded the data with **realistic ambiguity**. In one historical incident (INC-007), restarting Redis *was* the right call — because the Redis server itself was at 97% CPU and out of memory. So the agent can't just memorise "never restart Redis." It has to reason: **is Redis itself healthy, or is the application's pool the bottleneck?**

---

## Architecture

I kept it deliberately simple — a monolith, no microservices:

- **Frontend:** Next.js + TypeScript + Tailwind — a dark SRE-style dashboard
- **Backend:** Python + FastAPI + Pydantic
- **Memory:** Hindsight Cloud (official `hindsight-client` SDK)
- **LLM:** Groq (`openai/gpt-oss-120b` for diagnosis, `gpt-oss-20b` for the tool loop)
- **Data:** simulated telemetry, deployments and runbooks for 29 incidents

The browser only ever talks to FastAPI. API keys never leave the backend.

[📷 Diagram: Next.js → FastAPI → (Groq | Hindsight | local demo data)]

---

## How an investigation works

When you click **Investigate**, here's what actually happens:

**1. The agent plans.** The LLM receives the incident and a set of tools, and decides what to call:

- `get_service_health` — current telemetry
- `get_recent_deployments` — what changed recently
- `search_historical_incidents` — recall from Hindsight
- `get_runbook` — the team's documented procedure
- `get_incident` — full details of a past incident

The loop is capped at 5 tool iterations with retries, and handles malformed or unknown tool calls gracefully.

**2. It gathers current evidence.** For the demo incident: latency 4.8s, errors 18.4%, 1,842 Redis timeouts/min, connection pool at 100/100 — but the Redis *server* at a healthy 29% CPU. And a deploy 18 minutes ago added a Redis call to every payment request.

**3. It recalls memory.** Hindsight returns four past incidents with the same signature — and the INC-011 failure where restarting Redis backfired.

**4. It writes a structured diagnosis.** A final LLM call uses a strict JSON schema so the output is always well-formed:

```json
{
  "root_cause": "Redis connection pool exhaustion",
  "confidence": 0.9,
  "current_evidence": ["Redis pool 100/100", "Redis server CPU 29%", "..."],
  "historical_matches": [{"incident_id": "INC-011", "reason": "...", "outcome": "..."}],
  "failed_approaches": [{"incident_id": "INC-011", "action": "Restarted Redis primary", "result": "..."}],
  "learned_patterns": [{"pattern": "...", "source": "...", "from_engineer_feedback": false}],
  "recommended_actions": [{"action": "Increase the Redis connection pool", "rationale": "..."}],
  "warnings": ["Do not restart Redis — it failed in INC-011"]
}
```

Every step streams live to the UI, so what you see in the trace is what the backend is doing at that moment — not an animation.

[📷 Screenshot: Agent Activity trace + Hindsight Memory panel]

---

## The learning moment

This is the part of the demo I'm proudest of.

After the first diagnosis, OpsMind asks: **"Did OpsMind get it right?"**

The engineer clicks **Correct** and adds a note:

> *"Do not restart Redis for this failure pattern. The Redis server was healthy — runbook step 2 is outdated for this signature."*

When they click **Teach OpsMind**, two things are written to Hindsight:

- the **engineer's decision**, with the incident's failure signature
- a **reusable lesson**, generalised by the LLM from the feedback — for example: *"When payment-api shows Redis timeouts with the connection pool saturated while the Redis server is healthy, increase the application's pool and restart API workers; do not restart Redis."*

The UI shows the actual Hindsight document IDs that were created. Nothing is faked.

[📷 Screenshot: "✓ EXPERIENCE STORED" confirmation]

---

## Proof that it learned

Next, a new incident arrives: **INC-028**. Same service, similar symptoms — and this time the on-call engineer is proposing to restart the Redis cluster, because that's what the runbook says.

OpsMind investigates again. Hindsight recalls the lesson taught 30 seconds earlier, and the UI marks it **"NEW · LEARNED THIS SESSION"**. The recommendation lists it as **"TAUGHT BY ENGINEER"**, and adds a warning:

> *"Runbook step to restart the Redis cluster conflicts with engineer feedback and past failed attempts (INC-011)."*

A purple banner appears: **OPSMIND LEARNED.**

The best part: this is verifiable. Press **Reset**, which deletes only the taught lessons from Hindsight, and run INC-028 again — the engineer's lesson is gone from the evidence. The learning is real memory, not a scripted effect.

[📷 Screenshot: OPSMIND LEARNED banner + "NEW · LEARNED THIS SESSION" memory cards]

---

## Keeping it honest

AI demos are full of fake intelligence. I set myself strict rules:

- **No hard-coded diagnosis.** The LLM really calls tools and reasons. A third incident (INC-029, a database problem on a different service) gets a completely different root cause.
- **No fake memory.** Every memory card is a real Hindsight recall result.
- **No invented similarity scores.** The score on each card is Hindsight's own ranking value. No made-up "94% match".
- **No fake progress.** Trace steps turn green only when the backend reports them done.
- **No infrastructure changes.** OpsMind only recommends; it never executes remediation.

---

## Engineering challenges

**Free-tier rate limits.** Groq's free tier allows about 8,000 tokens per minute *per model*, and a single investigation initially used around 20,000. My fixes:

- Run the cheap tool-planning loop on a smaller model (`gpt-oss-20b`) and reserve the large model (`gpt-oss-120b`) for the final diagnosis.
- Keep token budgets tight, since Groq counts the maximum output length against your limit up front.
- **Model failover:** when one model is rate-limited, switch to another model's separate budget instead of waiting — and show that switch in the trace.

That brought the full demo — investigate, teach, investigate again — down to about 40 seconds.

**Getting the agent to respect lessons.** Early on, the agent recalled the engineer's lesson but still suggested restarting Redis "as a fallback" because the runbook said so. The fix was to make the evidence hierarchy explicit: engineer decisions that match the current failure signature outrank generic runbooks, and the agent must call out conflicts rather than paper over them.

**Recall precision.** A single semantic search sometimes ranked general incident facts above the one lesson that mattered. Adding a second, tag-filtered recall for failed approaches and engineer feedback made the important memories surface reliably.

---

## What's next

- **Real integrations:** live metrics from Datadog or Prometheus, incidents from PagerDuty, diagnoses posted to Slack
- **Postmortem ingestion:** upload existing postmortem PDFs and docs straight into Hindsight
- **Runbook auto-correction:** when team lessons repeatedly contradict a runbook, OpsMind drafts the fix
- **Service knowledge pages:** "everything we know about payment-api," generated from memory
- **Measuring impact:** time-to-resolution with vs. without memory

---

## Try it

The full source is on GitHub: **https://github.com/Sanjeev345/OpsMind**

```bash
cp .env.example .env    # add your Groq and Hindsight API keys
python -m backend.scripts.seed_hindsight
cd backend && uvicorn main:app --port 8000
cd frontend && npm install && npm run dev
```

Open `http://localhost:3000` and press **RUN DEMO**.

---

## Closing thought

The most valuable thing in an engineering organisation isn't its runbooks — it's the scar tissue from every incident it has survived. OpsMind is an attempt to make that scar tissue searchable, shareable, and present at 3 a.m. when it matters most.

An agent that remembers is useful. An agent that **learns from the people it works with** is something teams can actually trust.

