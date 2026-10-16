import { useEffect, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { ApiError, getProject, getProjectRisk } from '../api/client';
import type { ProjectDetail, ProjectRiskResponse } from '../api/types';
import { ErrorState, LoadingState, Section } from '../components/States';

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

function formatNumber(value: number | null | undefined, suffix = ''): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  return `${value}${suffix}`;
}

interface DetailState {
  project: ProjectDetail | null;
  risk: ProjectRiskResponse | null;
  error: string | null;
}

/**
 * Project detail (Phase 9.3).
 * Fetches GET /api/projects/{project_code} plus
 * GET /api/projects/{project_code}/risk.
 * Nullable values (e.g. time overrun probability) are shown as "—", never
 * replaced with zero. Risk visualization is intentionally deferred to 9.4.
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
            <p>{formatNumber(project.approval_date)}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Start date</p>
            <p>{formatNumber(project.start_date)}</p>
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

      <Section title="Risk assessment">
        <p className="muted">
          Persisted risk score and early warning from the backend risk engine.
        </p>
        <div className="detail-grid">
          <div className="detail-field">
            <p className="muted">Risk category</p>
            <p>
              <span className={riskChipClass(risk.risk_category)}>
                {risk.risk_category}
              </span>
            </p>
          </div>
          <div className="detail-field">
            <p className="muted">Score status</p>
            <p>{risk.score_status}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Combined risk score</p>
            <p>{formatNumber(risk.combined_risk_score)}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Cost overrun probability</p>
            <p>{formatNumber(risk.cost_overrun_probability, '%')}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Time overrun probability</p>
            <p>{formatNumber(risk.time_overrun_probability, '%')}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Missing component</p>
            <p>{risk.missing_component}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Warning type</p>
            <p>{risk.warning_type}</p>
          </div>
          <div className="detail-field">
            <p className="muted">Warning priority</p>
            <p>
              {risk.warning_priority} ({risk.warning_priority_label})
            </p>
          </div>
          <div className="detail-field" style={{ gridColumn: '1 / -1' }}>
            <p className="muted">Recommended action</p>
            <p>{risk.recommended_action}</p>
          </div>
          <div className="detail-field" style={{ gridColumn: '1 / -1' }}>
            <p className="muted">Risk indicators</p>
            <p>{risk.risk_indicators}</p>
          </div>
          <div className="detail-field" style={{ gridColumn: '1 / -1' }}>
            <p className="muted">Warning message</p>
            <p className="muted" style={{ color: 'var(--high)' }}>
              {risk.warning_message}
            </p>
          </div>
        </div>
      </Section>
    </div>
  );
}
