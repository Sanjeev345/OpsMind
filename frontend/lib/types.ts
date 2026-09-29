export type Severity = "SEV-1" | "SEV-2" | "SEV-3" | string;

export interface Metric {
  key: string;
  label: string;
  value: string;
  baseline?: string | null;
  status: "critical" | "warning" | "ok";
}

export interface Deployment {
  version: string;
  deployed_minutes_ago: number;
  author: string;
  change: string;
  status: string;
}

export interface Incident {
  id: string;
  title: string;
  timestamp: string;
  service: string;
  severity: Severity;
  status: string;
  summary: string;
  alerts: string[];
  metrics: Metric[];
  health: Record<string, Record<string, string> | string>;
  deployments: Deployment[];
}

export interface IncidentSummary {
  id: string;
  title: string;
  service: string;
  severity: Severity;
  status: string;
  timestamp: string;
  kind: "active" | "historical";
}

export interface TraceEvent {
  id: string;
  step: string;
  status: "running" | "completed" | "failed" | "warning";
  detail?: string | null;
  tool?: string | null;
  started_at: string;
  duration_ms?: number | null;
}

export interface MemoryItem {
  id: string;
  text: string;
  fact_type?: string | null;
  document_id?: string | null;
  memory_type?: string | null;
  incident_id?: string | null;
  mentioned_incidents: string[];
  source?: string | null;
  metadata: Record<string, string>;
  tags: string[];
  score?: number | null;
  occurred_at?: string | null;
  query?: string | null;
}

export interface Diagnosis {
  summary: string;
  root_cause: string;
  confidence: number;
  current_evidence: string[];
  historical_matches: { incident_id: string; reason: string; outcome: string }[];
  failed_approaches: { incident_id: string; action: string; result: string }[];
  learned_patterns: { pattern: string; source: string; from_engineer_feedback: boolean }[];
  recommended_actions: { action: string; rationale: string }[];
  warnings: string[];
}

export interface InvestigationResult {
  investigation_id: string;
  incident: Incident;
  diagnosis: Diagnosis | null;
  diagnosis_error?: string | null;
  memories: MemoryItem[];
  memory_status: "ok" | "unavailable" | "not_used";
  memory_error?: string | null;
  memory_queries: string[];
  trace: TraceEvent[];
  tool_calls: number;
  model: string;
  started_at: string;
  completed_at: string;
  duration_ms: number;
}

export interface Health {
  status: string;
  bank_id: string;
  model: string;
  hindsight: { configured: boolean; connected: boolean; bank_exists?: boolean; error?: string };
  groq: { configured: boolean; connected: boolean; model_available?: boolean; error?: string };
}

export interface MemoryStats {
  bank_id: string;
  total_memories: number;
  total_documents: number;
  total_links: number;
  total_observations: number;
  memories_by_type: Record<string, number>;
  pending_operations: number;
  last_memory_write_at?: string | null;
  engineer_lessons: number;
}

export interface FeedbackForm {
  correct: boolean | null;
  actual_root_cause: string;
  actual_resolution: string;
  engineer_note: string;
}

export interface FeedbackResult {
  stored: boolean;
  incident_id: string;
  bank_id: string;
  retained: { document_id: string; memory_type: string; content: string }[];
  lesson: string;
  lesson_generated_by: string;
  stored_at: string;
  memory_stats?: MemoryStats | null;
}

export type StreamEvent =
  | { type: "trace"; event: TraceEvent }
  | { type: "memories"; memories: MemoryItem[]; queries: string[] }
  | { type: "result"; result: InvestigationResult }
  | { type: "error"; code: string; message: string };
