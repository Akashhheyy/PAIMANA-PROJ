import { useEffect, useState } from 'react';
import { AlertTriangle, Search } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError, getEarlyWarnings } from '../api/client';
import type { EarlyWarningListResponse } from '../api/types';
import { EmptyState, ErrorState, LoadingState, Section } from '../components/States';
import { MetricCard } from '../components/MetricCard';

const PAGE_SIZES = [20, 50, 100] as const;

const VALID_RISK_CATEGORIES = ['Low', 'Medium', 'High', 'Unknown'];

function formatNumber(value: number | null | undefined, suffix = ''): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  return `${value}${suffix}`;
}

function riskChipClass(category: string | null): string {
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

function priorityChipClass(priority: string): string {
  const key = priority.trim().toLowerCase();
  switch (key) {
    case 'high':
      return 'risk-chip risk-chip--high';
    case 'medium':
      return 'risk-chip risk-chip--medium';
    case 'low':
      return 'risk-chip risk-chip--low';
    default:
      return 'risk-chip risk-chip--none';
  }
}

function countBy(items: EarlyWarningListResponse['items'], field: 'warning_priority' | 'warning_type', value: string): number {
  return items.filter((i) => i[field] === value).length;
}

interface EarlyWarningsPageState {
  data: EarlyWarningListResponse | null;
  error: string | null;
}

/**
 * Early Warnings (Phase 9.5).
 * Server-side filtered, paginated warning register backed by
 * GET /api/early-warnings. Every row and count comes from the backend -
 * nothing is fabricated. Null values are shown as "—", never zero-filled.
 */
export function EarlyWarningsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const [state, setState] = useState<EarlyWarningsPageState>({
    data: null,
    error: null,
  });
  const [loading, setLoading] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const page = Math.max(1, Number(searchParams.get('page')) || 1);
  const pageSizeRaw = Number(searchParams.get('page_size'));
  const validPageSizes = new Set<number>(PAGE_SIZES);
  const pageSize = validPageSizes.has(pageSizeRaw) ? PAGE_SIZES[0] : pageSizeRaw;
  const riskCategory = searchParams.get('risk_category') || undefined;
  const warningType = searchParams.get('warning_type') || undefined;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setState((prev) => ({ ...prev, error: null }));

    getEarlyWarnings({
      risk_category: riskCategory,
      warning_type: warningType,
      page,
      page_size: pageSize,
    })
      .then((data) => {
        if (!cancelled) setState({ data, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : 'Unexpected error loading early warnings.';
        setState({ data: null, error: message });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [page, pageSize, riskCategory, warningType, reloadKey]);

  const retry = () => setReloadKey((k) => k + 1);

  const data = state.data;
  const items = data?.items ?? [];
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / pageSize));
  const currentPage = Math.min(page, totalPages);
  const from =
    items.length > 0 ? (currentPage - 1) * pageSize + 1 : 0;
  const to = Math.min(from + items.length, data?.total ?? 0);

  const goPrev = () => {
    if (currentPage <= 1) return;
    setSearchParams({ page: String(currentPage - 1) });
  };
  const goNext = () => {
    if (currentPage >= totalPages) return;
    setSearchParams({ page: String(currentPage + 1) });
  };

  const setFilter = (key: 'risk_category' | 'warning_type', value: string) => {
    const params = new URLSearchParams(searchParams);
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    params.set('page', '1');
    setSearchParams(params);
  };

  const highCount = countBy(items, 'warning_priority', 'HIGH');
  const mediumCount = countBy(items, 'warning_priority', 'MEDIUM');
  const lowCount = countBy(items, 'warning_priority', 'LOW');

  if (loading || !data) {
    return <LoadingState label="Loading early warnings…" />;
  }
  if (state.error) {
    return <ErrorState message={state.error} onRetry={retry} />;
  }

  const riskCategoryOptions = VALID_RISK_CATEGORIES.filter((c) =>
    items.some((i) => i.risk_category === c),
  );
  const warningTypeOptions = Array.from(
    new Set(items.map((i) => i.warning_type)),
  ).sort();

  return (
    <div className="page">
      <Section
        title="Early Warnings"
        subtitle={`Active warnings from the risk engine · ${formatNumber(data.total)} total`}
      >
        <div className="metric-grid">
          <MetricCard
            label="Total warnings"
            value={data.total}
            hint="Early warnings persisted by the risk engine"
            icon={AlertTriangle}
          />
          <MetricCard
            label="High priority"
            value={highCount}
            hint="warning_priority = HIGH (current page)"
            tone="high"
          />
          <MetricCard
            label="Medium priority"
            value={mediumCount}
            hint="warning_priority = MEDIUM (current page)"
            tone="medium"
          />
          <MetricCard
            label="Low priority"
            value={lowCount}
            hint="warning_priority = LOW (current page)"
            tone="low"
          />
        </div>
        <div className="table-controls">
          <div className="search-field">
            <Search size={16} aria-hidden="true" />
            <span className="muted" style={{ fontSize: '0.82rem' }}>
              Filters:
            </span>
          </div>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: '0.82rem',
              color: 'var(--ink-soft)',
              whiteSpace: 'nowrap',
            }}
          >
            Risk category
            <select
              value={riskCategory ?? ''}
              onChange={(e) => setFilter('risk_category', e.target.value)}
              className="select"
            >
              <option value="">All</option>
              {riskCategoryOptions.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: '0.82rem',
              color: 'var(--ink-soft)',
              whiteSpace: 'nowrap',
            }}
          >
            Warning type
            <select
              value={warningType ?? ''}
              onChange={(e) => setFilter('warning_type', e.target.value)}
              className="select"
            >
              <option value="">All</option>
              {warningTypeOptions.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: '0.82rem',
              color: 'var(--ink-soft)',
              whiteSpace: 'nowrap',
            }}
          >
            Page size
            <select
              value={String(pageSize)}
              onChange={(e) =>
                setSearchParams({ page_size: e.target.value, page: '1' })
              }
              className="select"
            >
              {PAGE_SIZES.map((size) => (
                <option key={size} value={String(size)}>
                  {size}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Section>

      {items.length === 0 ? (
        <EmptyState
          message={
            data.total === 0
              ? 'No early warnings match the selected filters.'
              : 'No warnings on this page.'
          }
        />
      ) : (
        <>
          <div className="table-wrap">
            <table className="projects" aria-label="Early warnings register">
              <thead>
                <tr>
                  <th style={{ width: '12%' }}>Project code</th>
                  <th style={{ width: '26%' }}>Project name</th>
                  <th style={{ width: '16%' }}>Agency</th>
                  <th style={{ width: '10%' }}>State</th>
                  <th style={{ width: '10%' }}>Risk category</th>
                  <th style={{ width: '14%' }}>Warning type</th>
                  <th style={{ width: '12%' }}>Priority</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr
                    key={String(row.project_code)}
                    className="clickable"
                    role="button"
                    tabIndex={0}
                    aria-label={`View project ${row.project_code} - ${row.project_name} warning details`}
                    onClick={() => navigate(`/projects/${row.project_code}`)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        navigate(`/projects/${row.project_code}`);
                      }
                    }}
                  >
                    <td>{row.project_code}</td>
                    <td>{row.project_name}</td>
                    <td>{row.agency}</td>
                    <td>{row.state}</td>
                    <td>
                      <span className={riskChipClass(row.risk_category)}>
                        {row.risk_category}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.85rem' }}>
                      {row.warning_type}
                    </td>
                    <td>
                      <span className={priorityChipClass(row.warning_priority)}>
                        {row.warning_priority}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <span className="muted">
              Showing {from}-{to} of {formatNumber(data.total)}
            </span>
            <div className="pagination-controls">
              <button
                type="button"
                className="btn"
                disabled={currentPage <= 1}
                onClick={goPrev}
              >
                Prev
              </button>
              <span className="muted" style={{ margin: '0 8px' }}>
                Page {currentPage} of {totalPages}
              </span>
              <button
                type="button"
                className="btn"
                disabled={currentPage >= totalPages}
                onClick={goNext}
              >
                Next
              </button>
            </div>
          </div>

          {items.some((i) => i.time_overrun_probability === null) && (
            <p className="muted" style={{ marginTop: 10, fontSize: '0.82rem' }}>
              Some warnings have no time-overrun probability recorded (shown as
              "—"). This is not zero - the value is unavailable.
            </p>
          )}
        </>
      )}
    </div>
  );
}
