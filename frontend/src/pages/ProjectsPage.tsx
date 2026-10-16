import { useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError, getProjects } from '../api/client';
import type { ProjectListResponse } from '../api/types';
import { EmptyState, ErrorState, LoadingState, Section } from '../components/States';

const PAGE_SIZES = [20, 50, 100] as const;

function riskLabel(category: string | null): string {
  return category ?? 'Not scored';
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

function formatNumber(value: number | null | undefined, suffix = ''): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  return `${value}${suffix}`;
}

interface ProjectsPageState {
  data: ProjectListResponse | null;
  error: string | null;
}

/**
 * Project Explorer (Phase 9.3).
 * Paginated, searchable register backed by GET /api/projects.
 * Nothing is hardcoded - every row comes from the backend response.
 */
export function ProjectsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const [state, setState] = useState<ProjectsPageState>({
    data: null,
    error: null,
  });
  const [loading, setLoading] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const page = Math.max(1, Number(searchParams.get('page')) || 1);
  const pageSizeRaw = Number(searchParams.get('page_size'));
  const validPageSizes = new Set<number>(PAGE_SIZES);
  const pageSize = validPageSizes.has(pageSizeRaw) ? pageSizeRaw : PAGE_SIZES[0];
  const search = searchParams.get('search') || '';

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setState((prev) => ({ ...prev, error: null }));

    getProjects({
      page,
      page_size: pageSize,
      search: search || undefined,
    })
      .then((data) => {
        if (!cancelled) setState({ data, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : 'Unexpected error loading projects.';
        setState({ data: null, error: message });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [page, pageSize, search, reloadKey]);

  const retry = () => setReloadKey((k) => k + 1);

  const setSearch = (next: string) => {
    setSearchParams({ search: next, page: '1' });
  };

  const data = state.data;
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / pageSize));
  const currentPage = Math.min(page, totalPages);
  const from =
    data && data.items.length > 0 ? (currentPage - 1) * pageSize + 1 : 0;
  const to = Math.min(from + (data?.items.length ?? 0), data?.total ?? 0);

  const goPrev = () => {
    if (currentPage <= 1) return;
    setSearchParams({ page: String(currentPage - 1) });
  };
  const goNext = () => {
    if (currentPage >= totalPages) return;
    setSearchParams({ page: String(currentPage + 1) });
  };

  if (state.error) {
    return <ErrorState message={state.error} onRetry={retry} />;
  }
  if (loading || !data) {
    return <LoadingState label="Loading projects…" />;
  }

  return (
    <div className="page">
      <Section
        title="Project Explorer"
        subtitle={`Paginated project register · ${formatNumber(data.total)} projects tracked`}
      >
        <div className="table-controls">
          <div className="search-field">
            <Search size={16} aria-hidden="true" />
            <input
              type="search"
              placeholder="Search by name, code, agency or state…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search projects"
            />
          </div>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: '0.82rem',
              color: 'var(--ink-soft)',
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

      <Section
        title="Projects"
        subtitle={`Results for “${search || 'all projects'}”`}
        actions={
          <span className="muted">
            Rows are clickable - open a project to see its risk details.
          </span>
        }
      >
        {data.items.length === 0 ? (
          <EmptyState message={`No projects match “${search}”.`} />
        ) : (
          <>
            <div className="table-wrap">
              <table className="projects" aria-label="Project register">
                <thead>
                  <tr>
                    <th style={{ width: '14%' }}>Project code</th>
                    <th style={{ width: '30%' }}>Project name</th>
                    <th style={{ width: '18%' }}>Agency</th>
                    <th style={{ width: '12%' }}>State</th>
                    <th style={{ width: '14%' }}>Report month</th>
                    <th style={{ width: '12%' }}>Risk category</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((row) => (
                    <tr
                      key={String(row.project_code)}
                      className="clickable"
                      role="button"
                      tabIndex={0}
                      aria-label={`View project ${row.project_code} - ${row.project_name}`}
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
                      <td>{row.report_month}</td>
                      <td>
                        <span className={riskChipClass(row.risk_category)}>
                          {riskLabel(row.risk_category)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Section>

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
    </div>
  );
}
