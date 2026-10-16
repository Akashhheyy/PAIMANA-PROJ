/**
 * Response types mirroring the backend Pydantic schemas EXACTLY
 * (backend/app/schemas/*.py). Nullable fields stay `| null` - the 354
 * partial-score projects have a null time probability that must never be
 * replaced with 0.
 */

/** RiskSummaryResponse (schemas/risk.py) */
export interface RiskSummaryResponse {
  total_projects: number;
  high_risk_count: number;
  medium_risk_count: number;
  low_risk_count: number;
  partial_incomplete_count: number;
  cost_warning_count: number;
  time_warning_count: number;
  combined_high_risk_warning_count: number;
}

/** ProgressBin (schemas/dashboard.py) */
export interface ProgressBin {
  label: string;
  count: number;
}

/** ProgressDistributionResponse (schemas/dashboard.py) */
export interface ProgressDistributionResponse {
  snapshot_label: string;
  total_projects: number;
  projects_included: number;
  projects_missing_progress: number;
  bins: ProgressBin[];
  mean_progress: number | null;
  median_progress: number | null;
  agency_filter: string | null;
  state_filter: string | null;
}

/** ProjectSummary (schemas/projects.py) */
export interface ProjectSummary {
  project_code: number;
  project_name: string;
  state: string;
  agency: string;
  report_month: string;
  risk_category: string | null;
}

/** ProjectListResponse (schemas/projects.py) */
export interface ProjectListResponse {
  items: ProjectSummary[];
  page: number;
  page_size: number;
  total: number;
}

/** EarlyWarningItem (schemas/warnings.py) */
export interface EarlyWarningItem {
  project_code: number;
  project_name: string;
  state: string;
  agency: string;
  report_month: string | null;
  cost_overrun_probability: number | null;
  time_overrun_probability: number | null;
  combined_risk_score: number | null;
  risk_category: string;
  score_status: string;
  missing_component: string;
  warning_type: string;
  warning_priority: string;
  warning_priority_label: string;
  warning_message: string;
  risk_indicators: string;
  recommended_action: string;
}

/** EarlyWarningListResponse (schemas/warnings.py) */
export interface EarlyWarningListResponse {
  items: EarlyWarningItem[];
  page: number;
  page_size: number;
  total: number;
  risk_category: string | null;
  warning_type: string | null;
}

/** HealthResponse (schemas/__init__.py) */
export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

/** ProjectDetail (schemas/projects.py) */
export interface ProjectDetail {
  project_code: number;
  project_name: string;
  state: string;
  agency: string;
  report_month: string;
  risk_category: string | null;
  approval_date: string | null;
  start_date: string | null;
  target_doc: string | null;
  revised_doc: string | null;
  original_cost_crore: number | null;
  revised_cost_crore: number | null;
  cumulative_expenditure_crore: number | null;
  physical_progress_pct: number | null;
  planned_horizon_months: number | null;
}

/** ProjectRiskResponse (schemas/risk.py) */
export interface ProjectRiskResponse {
  project_code: number;
  project_name: string;
  state: string;
  agency: string;
  report_month: string | null;
  cost_overrun_probability: number | null;
  time_overrun_probability: number | null;
  combined_risk_score: number | null;
  risk_category: string;
  score_status: string;
  missing_component: string;
  warning_type: string;
  warning_priority: string;
  warning_priority_label: string;
  warning_message: string;
  risk_indicators: string;
  recommended_action: string;
}

