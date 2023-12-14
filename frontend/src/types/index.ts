export type Status = 'supported' | 'partially_supported' | 'contradicted' | 'insufficient_evidence' | 'citation_missing' | 'source_unavailable' | 'needs_human_review' | 'not_applicable';
export type AnalysisState = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type Page = 'dashboard' | 'new' | 'batch' | 'reviews' | 'history' | 'settings' | 'help' | 'result';

export interface AnalysisSummary {
  id: string; title: string; mode: string; status: AnalysisState; progress: number; provider: string; use_ai: boolean;
  created_at: string; updated_at: string; completed_at?: string | null; total_claims: number; status_counts: Record<string, number>; error?: string | null; batch_id?: string | null;
}
export interface Citation {
  id: string; raw: string; url?: string | null; kind: string; resolution_status: string; title_mismatch: boolean;
  source?: { id: string; title: string; url?: string | null; status: string; error?: string | null } | null;
}
export interface Evidence {
  id: string; source_id: string; source_title: string; source_url?: string | null; page?: number | null; section?: string | null;
  text: string; start_char: number; end_char: number; relevance: number; rank: number; content_hash: string;
}
export interface Review {
  id: string; decision: string; notes: string; reviewer: string; created_at: string;
}
export interface Claim {
  id: string; ordinal: number; text: string; normalized_text: string; start_char: number; end_char: number; kind: string; status: Status;
  reasoning: string; assessor: string; uncertainty: string; assessment_meta: Record<string, unknown>; citations: Citation[]; evidence: Evidence[]; reviews: Review[];
}
export interface SourceInfo {
  id: string; external_id?: string | null; title: string; url?: string | null; source_type: string; status: string; error?: string | null;
  content_hash?: string | null; retrieved_at?: string | null; characters: number; metadata: Record<string, unknown>;
}
export interface AnalysisDetail extends AnalysisSummary {
  input_text: string; settings: Record<string, unknown>; result_meta: Record<string, unknown>; sources: SourceInfo[]; claims: Claim[];
}
export interface DashboardData { recent: AnalysisSummary[]; total_analyses: number; total_claims: number; status_counts: Record<string, number>; pending_reviews: number; }
export interface ReviewQueueItem {
  id: string; analysis_id: string; analysis_title: string; claim: string; normalized_claim: string; status: Status; reasoning: string; uncertainty: string;
  reviewed: boolean; latest_review?: { decision: string; notes: string; reviewer: string; created_at: string } | null;
  evidence: { source_title: string; source_url?: string | null; text: string; page?: number | null }[];
}
export interface ProviderSettings {
  provider: string; base_url?: string | null; model?: string | null; has_api_key: boolean; secret_storage: string; temperature: number; max_output_tokens: number;
  timeout_seconds: number; retries: number; analysis_token_budget: number; daily_token_budget: number; daily_usage_estimate?: number; remaining_daily_tokens?: number;
}
export interface ProviderPreset {
  id: string; label: string; tagline: string; description: string;
  base_url: string | null; auth: string; key_required: boolean;
  key_placeholder: string; key_help: string; model_placeholder: string; model_help: string;
  cost_tier: 'free' | 'usage' | 'varies'; cost_note: string; setup: string[];
}
export interface ApiError { detail?: string | { msg?: string }[]; }
