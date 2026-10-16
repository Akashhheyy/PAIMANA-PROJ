import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CircleCheck,
  CircleMinus,
  CircleAlert,
  FolderKanban,
} from 'lucide-react';
import { ApiError, getProgressDistribution, getRiskSummary } from '../api/client';
import type { ProgressDistributionResponse, RiskSummaryResponse } from '../api/types';
import { MetricCard } from '../components/MetricCard';
import { ProgressChart } from '../components/ProgressChart';
import { ErrorState, LoadingState, Section } from '../components/States';

interface DashboardState {
  summary: RiskSummaryResponse | null;
  progress: ProgressDistributionResponse | null;
  error: string | null;
}

function formatStat(value: number | null | undefined, suffix = ''): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  return `${value}${suffix}`;
}

export function OverviewPage() {
  const [state, setState] = useState<DashboardState>({
    summary: null,
    progress: null,
    error: null,
  });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState((prev) => ({ ...prev, error: null }));
    Promise.all([getRiskSummary(), getProgressDistribution()])
      .then(([summary, progress]) => {
        if (!cancelled) setState({ summary, progress, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : 'Unexpected error while loading dashboard data.';
        setState({ summary: null, progress: null, error: message });
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);

  if (state.error) {
    return <ErrorState message={state.error} onRetry={retry} />;
  }
  if (!state.summary || !state.progress) {
    return <LoadingState label="Loading dashboard data…" />;
  }

  const { summary, progress } = state;

  return (
    <div className="page">
      <div className="metric-grid" data-testid="summary-cards">
        <MetricCard
          label="Total projects"
          value={summary.total_projects}
          hint="April 2026 snapshot"
          icon={FolderKanban}
        />
        <MetricCard
          label="High-risk projects"
          value={summary.high_risk_count}
          hint="risk_category = High"
          icon={CircleAlert}
          tone="high"
        />
        <MetricCard
          label="Medium-risk projects"
          value={summary.medium_risk_count}
          hint="risk_category = Medium"
          icon={CircleMinus}
          tone="medium"
        />
        <MetricCard
          label="Low-risk projects"
          value={summary.low_risk_count}
          hint="risk_category = Low"
          icon={CircleCheck}
          tone="low"
        />
      </div>

      <Section
        title="Overall project progress"
        subtitle={`Physical progress of monitored projects · ${progress.snapshot_label} snapshot`}
        actions={
          <div className="stat-pills" aria-label="Progress statistics">
            <span className="pill">
              Mean <strong>{formatStat(progress.mean_progress, '%')}</strong>
            </span>
            <span className="pill">
              Median <strong>{formatStat(progress.median_progress, '%')}</strong>
            </span>
            <span className="pill">
              Projects <strong>{progress.total_projects}</strong>
            </span>
          </div>
        }
      >
        <ProgressChart bins={progress.bins} snapshotLabel={progress.snapshot_label} />
        <p className="chart-caption muted">
          Distribution across {progress.bins.length} progress ranges, from{' '}
          <strong>{progress.snapshot_label}</strong>. {progress.projects_included}{' '}
          project{progress.projects_included === 1 ? '' : 's'} included,{' '}
          {progress.projects_missing_progress} without recorded progress (excluded
          from the chart, never counted as zero).
        </p>
      </Section>

      <Section
        title="Data completeness & warning totals"
        subtitle="Counts reported directly by the risk and early-warning endpoints"
      >
        <div className="chip-row">
          <span className="chip chip-amber">
            <AlertTriangle size={14} aria-hidden="true" />
            Partial risk scores: {summary.partial_incomplete_count}
          </span>
          <span className="chip">Cost warnings: {summary.cost_warning_count}</span>
          <span className="chip">Time warnings: {summary.time_warning_count}</span>
          <span className="chip">
            Combined high-risk warnings: {summary.combined_high_risk_warning_count}
          </span>
        </div>
      </Section>

      <p className="snapshot-note" role="note">
        This dashboard analyses the available April 2026 snapshot. Predictions are
        prototype risk estimates and are not yet validated as future forecasts
        using multiple historical snapshots.
      </p>
    </div>
  );
}
