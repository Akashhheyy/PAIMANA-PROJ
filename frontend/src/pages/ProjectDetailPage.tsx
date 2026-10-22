import { useEffect, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { ApiError, getProject, getProjectRisk } from '../api/client';
import type { ProjectDetail, ProjectRiskResponse } from '../api/types';
import { ErrorState, LoadingState, Section } from '../components/States';
import { MetricCard } from '../components/MetricCard';
import { RiskComparisonChart } from '../components/RiskComparisonChart';

function riskChipClass(category: string): string {
  switch (category) {
    case 'High':
      return 'risk-chip risk-chip--high';
    case 'Medium':
      return 'risk-chip risk-chip--medium';
    case 'Low':
      return 'risk-chip risk-chip--low';
    default:
      return 'risk-chip risk-chip--none';
  }
}

function formatDate(value: string | null | undefined): string {
  if (value === null || value === undefined) {
    return '—';
  }
  return value;
}

function formatNumber(value: number | null | undefined, suffix = ''): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  return `${value}${suffix}`;
}

/** Format a 0-1 probability fraction as a percentage with 2 decimal places. */
function formatProbability(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  return `${(value * 100).toFixed(2)}%`;
}

/** Format a 0-1 risk score fraction to 3 decimal places. */
function formatRiskScore(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  return value.toFixed(3);
}

interface DetailState {
  project: ProjectDetail | null;
  risk: ProjectRiskResponse | null;
  error: string | null;
}

/**
 * Project detail (Phase 9.4).
 * Fetches GET /api/projects/{project_code} plus
 * GET /api/projects/{project_code}/risk.
 * Displays cost-overrun and time-overrun probability cards, a comparison
 * chart, combined score/category, and all project and warning fields from the
 * backend. Nullable values (e.g. time overrun probability) are shown as "—",
 * never replaced with zero.
 */
export function ProjectDetailPage() {
  const { projectCode } = useParams<{ projectCode: string }>();
  const navigate = useNavigate();

  const [state, setState] = useState<DetailState>({
    project: null,
    risk: null,
    error: null,
  });
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!projectCode) {
      setState({
        project: null,
        risk: null,
        error: 'No project code provided.',
      });
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setState((prev) => ({ ...prev, error: null }));

    Promise.all([getProject(projectCode), getProjectRisk(projectCode)])
      .then(([project, risk]) => {
        if (!cancelled) setState({ project, risk, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setState({
            project: null,
            risk: null,
            error: `Project “${projectCode}” not found in the current snapshot.`,
          });
        } else {
          setState({
            project: null,
            risk: null,
            error:
              err instanceof ApiError
                ? err.message
                : 'Unexpected error loading project details.',
          });
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectCode, reloadKey]);

  const retry = () => setReloadKey((k) => k + 1);

  if (loading || (!state.project && !state.error)) {
    return <LoadingState label="Loading project details…" />;
  }
  if (state.error) {
    return (
      <div className="page">
        <ErrorState message={state.error} onRetry={retry} />
      </div>
    );
  }

  const project = state.project;
  const risk = state.risk;
  if (!project || !risk) {
    return <LoadingState label="Loading project details…" />;
  }

  return (
    <div className="page">
      <Section
        title={project.project_name}
        subtitle={`Project ${project.project_code} - ${project.agency}, ${project.state}`}
        actions={
          <button
            type="button"
            className="btn"
            onClick={() => navigate(-1)}
          >
            <ArrowLeft size={16} aria-hidden="true" /> Back to projects
          </button>
        }
      >
        <div className="detail-header">
          <span className="chip">{project.project_code}</span>
          <span className="chip">{project.agency}</span>
          <span className="chip">{project.state}</span>
          <span className="chip">{project.report_month}</span>
          <span
            className={
              project.risk_category
                ? riskChipClass(project.risk_category)
                : 'risk-chip risk-chip--none'
            }
          >
            {project.risk_category ?? 'Not scored'}
          </span>
        </div>
      </Section>

      <Section title="Project information">
        <div className="detail-grid">
          <div className="detail-field">
            <p className="muted">Project code</p>
            <p>{project.project_code}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Agency</p>
            <p>{project.agency}</p>
          </div>
          <div className="detail-field">
            <p className="muted">State</p>
            <p>{project.state}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Report month</p>
            <p>{project.report_month}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Risk category</p>
            <p>{project.risk_category ?? '—'}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Approval date</p>
            <p>{formatDate(project.approval_date)}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Start date</p>
            <p>{formatDate(project.start_date)}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Physical progress</p>
            <p>{formatNumber(project.physical_progress_pct, '%')}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Original cost</p>
            <p>{formatNumber(project.original_cost_crore, ' crore')}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Revised cost</p>
            <p>{formatNumber(project.revised_cost_crore, ' crore')}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Cumulative expenditure</p>
            <p>{formatNumber(project.cumulative_expenditure_crore, ' crore')}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Planned horizon</p>
            <p>{formatNumber(project.planned_horizon_months, ' months')}</p>
          </div>
        </div>
      </Section>

      <Section
        title="Risk assessment"
        subtitle="Cost and schedule risk probabilities, combined score, and early warning from the backend risk engine"
      >
        <div className="risk-summary-row">
          <MetricCard
            label="Cost overrun probability"
            value={formatProbability(risk.cost_overrun_probability)}
            tone="high"
            className="metric-card--probability"
          />
          <MetricCard
            label="Time overrun probability"
            value={formatProbability(risk.time_overrun_probability)}
            tone="medium"
            className="metric-card--probability"
          />
          <MetricCard
            label="Combined risk score"
            value={formatRiskScore(risk.combined_risk_score)}
            tone={risk.risk_category as
              | 'high'
              | 'medium'
              | 'low'
              | 'default'}
            className="metric-card--accent"
          />
          <div className="metric-card">
            <div className="metric-top">
              <span className="metric-label">Risk category</span>
              <span
                className={riskChipClass(risk.risk_category)}
              >
                {risk.risk_category}
              </span>
            </div>
            <p className="metric-value">{risk.risk_category}</p>
          </div>
        </div>

        <RiskComparisonChart
          costProbability={risk.cost_overrun_probability}
          timeProbability={risk.time_overrun_probability}
        />
      </Section>

      <Section title="Early warning details">
        <div className="warning-panel">
          <p>
            <strong>Warning type:</strong> {risk.warning_type}
          </p>
          <p>
            <strong>Priority:</strong> {risk.warning_priority} (
            {risk.warning_priority_label})
          </p>
          <p>
            <strong>Score status:</strong> {risk.score_status}
          </p>
          <p>
            <strong>Missing component:</strong> {risk.missing_component}
          </p>
          <p>
            <strong>Recommended action:</strong> {risk.recommended_action}
          </p>
          <p>
            <strong>Risk indicators:</strong> {risk.risk_indicators}
          </p>
          <p>
            <strong>Warning message:</strong>{' '}
            <span className="muted" style={{ color: 'var(--high)' }}>
              {risk.warning_message}
            </span>
          </p>
        </div>
      </Section>
    </div>
  );
}
