/**
 * Domain types mirroring the backend API contract.
 *
 * These are the single source of truth for response shapes on the client;
 * components and hooks import from here rather than declaring inline types.
 */

export type RunStatus =
  | 'pending'
  | 'analyzing'
  | 'awaiting_review'
  | 'running'
  | 'packaging'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type AgentStatus = 'waiting' | 'running' | 'completed' | 'skipped' | 'failed';

export type LogLevel = 'debug' | 'info' | 'warning' | 'error';

export type AdapterKind = 'frontend' | 'backend' | 'database';

export type Theme = 'dark' | 'light';

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_admin: boolean;
  theme_preference: string;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
}

export interface AuthenticatedResponse {
  user: User;
  tokens: TokenPair;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  idea: string;
  summary: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
  analysis?: RequirementAnalysis | null;
  tech_stack?: TechStack | null;
  run_count?: number;
  latest_run_id?: string | null;
  latest_run_status?: string | null;
}

export interface Paged<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface DashboardStats {
  total_projects: number;
  total_runs: number;
  completed_runs: number;
  total_files_generated: number;
  total_generation_seconds: number;
  active_runs: number;
}

export interface Capabilities {
  needs_authentication: boolean;
  needs_database: boolean;
  needs_api: boolean;
  needs_backend: boolean;
  needs_frontend: boolean;
}

export interface FunctionalRequirement {
  id: string;
  title: string;
  description: string;
  priority: 'must' | 'should' | 'could';
  module: string;
}

export interface NonFunctionalRequirement {
  id: string;
  category: string;
  requirement: string;
}

export interface UserStory {
  id: string;
  story: string;
  acceptance_criteria: string[];
}

export interface UseCase {
  id: string;
  name: string;
  actor: string;
  main_flow: string[];
  alternate_flow: string;
}

export interface RequirementAnalysis {
  executive_summary: string;
  project_overview: string;
  scope_in: string[];
  scope_out: string[];
  functional_requirements: FunctionalRequirement[];
  non_functional_requirements: NonFunctionalRequirement[];
  user_stories: UserStory[];
  use_cases: UseCase[];
  actors: string[];
  entities: string[];
  assumptions: string[];
  clarifications: string[];
  capabilities: Capabilities;
  complexity: 'minimal' | 'standard' | 'advanced' | 'enterprise';
  rationale: string;
}

export interface TechStack {
  frontend: string | null;
  backend: string | null;
  database: string | null;
  authentication: string | null;
  rationale: Record<string, string>;
  user_customised: boolean;
}

export interface ScoredOption {
  key: string;
  display_name: string;
  score: number;
  reasons: string[];
}

export interface WorkflowStep {
  role: string;
  display_name: string;
  sequence: number;
  status: AgentStatus;
  skip_reason: string;
  depends_on: string[];
}

export interface AnalysisResult {
  project_id: string;
  analysis: RequirementAnalysis;
  recommended_stack: TechStack;
  options: Record<AdapterKind, ScoredOption[]>;
  workflow_preview: WorkflowStep[];
}

export interface AgentExecution {
  role: string;
  display_name: string;
  sequence: number;
  status: AgentStatus;
  progress: number;
  summary: string | null;
  skip_reason: string | null;
  error_message: string | null;
  confidence: number | null;
  files_produced: number;
  duration_seconds: number | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface Run {
  id: string;
  project_id: string;
  status: RunStatus;
  phase: string | null;
  progress: number;
  file_count: number;
  duration_seconds: number | null;
  created_at: string;
  finished_at: string | null;
  project_name?: string | null;
  tech_stack?: TechStack | null;
  analysis?: RequirementAnalysis | null;
  workflow_plan?: WorkflowStep[] | null;
  report?: GenerationReport | null;
  error_message?: string | null;
  agents?: AgentExecution[];
  artifact_count?: number;
  input_tokens?: number;
  output_tokens?: number;
  cached_tokens?: number;
}

export interface RunEvent {
  sequence: number;
  type: string;
  level: LogLevel;
  agent: string | null;
  message: string;
  payload: Record<string, unknown> | null;
  timestamp: string;
}

export interface ArtifactChecklistItem {
  name: string;
  delivered: boolean;
  detail: string;
}

export interface GenerationReport {
  generated_at: string;
  generator: { name: string; version: string };
  project: {
    name: string;
    slug: string;
    idea: string;
    summary: string;
    complexity: string;
  };
  stack: TechStack;
  capabilities: Record<string, boolean>;
  timing: { duration_seconds: number; duration_display: string };
  agents: {
    total: number;
    executed: number;
    skipped: number;
    failed: number;
    detail: Array<{
      role: string;
      display_name: string;
      status: AgentStatus;
      summary: string;
      duration_seconds: number;
      files_produced: number;
      confidence: number | null;
      warnings: string[];
    }>;
  };
  artifacts: ArtifactChecklistItem[];
  statistics: {
    file_count: number;
    total_bytes: number;
    total_lines: number;
    by_extension: Record<string, number>;
    by_agent: Record<string, number>;
    rejected_count: number;
  };
  usage: {
    input_tokens: number;
    output_tokens: number;
    cache_read_tokens: number;
    cache_write_tokens: number;
    total_tokens: number;
  };
  confidence: { dimensions: Record<string, number>; overall: number };
  effort_saved: {
    hours_low: number;
    hours_high: number;
    weeks_low: number;
    weeks_high: number;
    display: string;
    basis: string[];
  };
  quality: {
    review_score: number;
    issues_found: number;
    blocking_issues: number;
    issues_resolved: number;
    test_files: number;
    assessment: string;
  };
  package: { filename: string | null; size_bytes: number; file_count: number };
  status: string;
  status_detail: string;
}

export interface Artifact {
  id: string;
  kind: string;
  name: string;
  description: string | null;
  produced_by: string | null;
  version: number;
  content_type: string;
  size_bytes: number;
  is_downloadable: boolean;
  created_at: string;
  content?: string | null;
  artifact_metadata?: Record<string, unknown> | null;
}

export interface WorkspaceFile {
  path: string;
  description: string;
  produced_by: string | null;
  size_bytes: number;
  line_count: number;
}

export interface AdapterDescriptor {
  key: string;
  display_name: string;
  kind: AdapterKind;
  language: string;
  version: string;
  description: string;
  tags: string[];
  best_for: string[];
}

export interface AgentDescriptor {
  role: string;
  display_name: string;
  description: string;
  depends_on: string;
}

export interface Catalogue {
  frontend: AdapterDescriptor[];
  backend: AdapterDescriptor[];
  database: AdapterDescriptor[];
  agents: AgentDescriptor[];
}

export interface HealthStatus {
  status: string;
  version: string;
  environment: string;
  database: string;
  llm_configured: boolean;
  active_runs: number;
}

/** Live health for one model provider, from `GET /providers`. */
export interface ProviderHealth {
  key: string;
  display_name: string;
  model: string;
  priority: number;
  status: 'healthy' | 'degraded' | 'cooling_down' | 'unconfigured' | 'disabled';
  enabled: boolean;
  configured: boolean;
  selectable: boolean;
  requests: number;
  successes: number;
  failures: number;
  retries: number;
  failovers_from: number;
  failovers_to: number;
  success_rate: number;
  consecutive_failures: number;
  latency_ms: number;
  last_latency_ms: number;
  last_error: string;
  last_error_kind: string;
  last_success_at: string | null;
  last_failure_at: string | null;
  cooldown_remaining_seconds: number;
  cooldown_reason: string;
  input_tokens: number;
  output_tokens: number;
}

export interface CacheStats {
  hits: number;
  misses: number;
  stores: number;
  evictions: number;
  lookups: number;
  hit_rate: number;
}

export interface ProviderTotals {
  requests: number;
  successes: number;
  failures: number;
  retries: number;
  failovers: number;
  cache_hits: number;
  cache_misses: number;
  cache_hit_rate: number;
  success_rate: number;
  active_provider: string;
}

export interface ProviderDashboard {
  providers: ProviderHealth[];
  totals: ProviderTotals;
  cache: CacheStats;
  priority: string[];
  available_providers: string[];
  active_provider: string;
  failover_enabled: boolean;
  task_routing_enabled: boolean;
  cache_enabled: boolean;
  retry_limit: number;
}
