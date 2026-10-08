// Tipi speculari ai modelli Pydantic del backend (app/schemas, app/service/runs.py)

export type RunStatus = "queued" | "analyzing" | "review" | "generating" | "done" | "error" | "interrupted";
export type Provider = "anthropic" | "openai" | "gemini";
export type Tier = "strong" | "fast";

export interface SubProfile {
  name: string;
  min_requirements: string[];
  preferred: string[];
  certifications: string[];
}

export interface ProfileSpec {
  id: string;
  name: string;
  name_local?: string | null;
  purpose: string;
  responsibilities: string[];
  skills_required: string[];
  min_requirements: string[];
  preferred: string[];
  certifications: string[];
  subprofiles: SubProfile[];
  min_years_total?: number | null;
  min_years_role?: number | null;
}

export interface BandoSpec {
  language: string;
  title: string;
  general_requirements: string[];
  profiles: ProfileSpec[];
}

export interface CVExperience {
  company?: string | null;
  role?: string | null;
  client?: string | null;
  project?: string | null;
  start?: string | null;
  end?: string | null;
  is_current: boolean;
  technologies: string[];
}

export interface CVCanonical {
  source_file: string;
  full_name?: string | null;
  email?: string | null;
  phone?: string | null;
  location?: string | null;
  headline?: string | null;
  experiences: CVExperience[];
  certifications: string[];
  skills: string[];
}

export interface Assignment {
  profile_id: string;
  subprofile?: string | null;
  confidence: number;
  rationale: string;
}

export interface ExperienceBlock {
  title: string;
  role: string;
  period?: string | null;
  bullets: string[];
  source_indices: number[];
}

export interface RequirementCoverage {
  requirement: string;
  status: "met" | "partial" | "not_evidenced" | string;
  evidence: string;
}

export interface PersonContent {
  source_file: string;
  profile_id: string;
  profile_name: string;
  full_name: string;
  name_is_placeholder: boolean;
  phone?: string | null;
  email?: string | null;
  current_role?: string | null;
  current_company?: string | null;
  total_experience?: string | null;
  domicile?: string | null;
  summary: string;
  background: string[];
  skills: string[];
  experiences: ExperienceBlock[];
  coverage: RequirementCoverage[];
  omitted: string[];
  warnings: string[];
}

export interface FitIssue {
  slide: number;
  slot: string;
  detail: string;
  severity: string;
}

export interface FaithIssue {
  slot: string;
  text: string;
  reason: string;
  severity: "low" | "medium" | "high" | string;
}

export interface PersonReport {
  content: PersonContent;
  fit_iterations: number;
  fit_issues: FitIssue[];
  fit_notes: string[];
  faith_issues: FaithIssue[];
  visual_notes: string[];
  slides: number[];
}

export interface GenerationReport {
  language: string;
  template_name: string;
  people: PersonReport[];
  notes: string[];
}

export interface RunResultInfo {
  pptx: string;
  report_md: string;
  report_json: string;
  slides: string[];
  report: GenerationReport;
  generated_at: string;
  duration_s: number;
  edited: boolean;
  pending_edits: boolean;
}

export interface LogEntry {
  ts: string;
  stage: string;
  msg: string;
  level: string;
}

export interface CostAgg {
  key?: string | null;
  calls: number;
  cost_usd: number;
  saved_usd: number;
  input_tokens: number;
  output_tokens: number;
  thinking_tokens: number;
  cache_read_tokens: number;
  cache_hits: number;
  errors: number;
  unpriced: number;
  avg_latency_ms: number;
}

export interface Run {
  id: string;
  created_at: string;
  updated_at: string;
  title: string;
  status: RunStatus;
  stage: string;
  progress: number;
  message: string;
  error?: string | null;
  options: { visual_critic: boolean };
  provider: string;
  models: Partial<Record<Tier, string>>;
  bando_file: string;
  cv_files: string[];
  template_file?: string | null;
  bando?: BandoSpec | null;
  cvs: CVCanonical[];
  assignments: Record<string, Assignment>;
  result?: RunResultInfo | null;
  log: LogEntry[];
  cost: { totals: CostAgg; by_stage: CostAgg[]; by_phase: CostAgg[] };
  event_seq: number;
}

export interface RunSummary {
  id: string;
  title: string;
  status: RunStatus;
  created_at: string;
  updated_at: string;
  n_cvs: number;
  provider: string;
  language?: string | null;
  has_result: boolean;
  cost_usd: number;
  calls: number;
}

export interface Estimate {
  currency: string;
  min: number;
  max: number;
  expected: number;
  spent_so_far: number;
  calls_so_far: number;
  per_cv: { file: string; min: number; max: number; expected: number }[];
  models: Partial<Record<Tier, string>>;
  provider?: string;
  run_budget_remaining?: number | null;
  notes: string[];
}

export interface Status {
  provider: string;
  configured: boolean;
  models: Partial<Record<Tier, string>>;
  renderer: string;
  version: string;
}

export interface SettingsView {
  provider: string;
  resolved_provider: string;
  keys: Record<Provider, { set: boolean; masked: string }>;
  models: Record<Provider, Record<Tier, string>>;
  default_models: Record<Provider, Record<Tier, string>>;
  reasoning: Record<Tier, string>;
  reasoning_levels: string[];
  run_budget_usd: number;
  monthly_budget_usd: number;
  max_experiences: number;
  max_fit_iterations: number;
}

export interface PriceTier {
  from: string;
  input: number;
  output: number;
  cache_read?: number;
  cache_write?: number;
}

export interface PriceRow {
  model: string;
  provider: string;
  label: string;
  verified?: boolean;
  overridden?: boolean;
  tiers: PriceTier[];
  current: { input: number; output: number; cache_read: number; cache_write: number } | null;
}

export interface CostSummary {
  days: number;
  start: string | null;
  totals: CostAgg;
  by_day: CostAgg[];
  by_day_model: { day: string; model: string; cost_usd: number; calls: number }[];
  by_model: CostAgg[];
  by_stage: (CostAgg & { label: string })[];
  by_run: (CostAgg & { title: string })[];
  month_to_date: number;
  monthly_budget_usd: number;
  run_budget_usd: number;
  avg_cost_per_cv: number | null;
  cvs_processed: number;
}

export interface LLMCall {
  id: number;
  ts: string;
  run_id: string | null;
  phase: string | null;
  stage: string;
  stage_label: string;
  task: string;
  provider: string;
  model: string;
  tier: string;
  input_tokens: number;
  output_tokens: number;
  thinking_tokens: number;
  cache_read_tokens: number;
  cost_usd: number;
  saved_usd: number;
  price_known: number;
  local_cache_hit: number;
  latency_ms: number;
  attempts: number;
  status: string;
  error: string | null;
}

export interface LiveCall {
  stage: string;
  task: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  thinking_tokens: number;
  cost_usd: number;
  local_cache_hit: number;
  latency_ms: number;
}
